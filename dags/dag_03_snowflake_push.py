"""
DAG 3: Push the flat Postgres tables to Snowflake SYNTHEA_PROD.PUBLIC through Snowpipe.

Snowpipe is serverless (billed per GB loaded), so this DAG never wakes a warehouse:
  1. each flat table is written to Parquet files and PUT to @SNOWPIPE_STAGE/<table>/
  2. the table's pipe (<TABLE>_PIPE) is notified through the Snowpipe REST API (key-pair JWT)
  3. the DAG waits until every file reports LOADED with the expected row count, then
     removes the loaded files from the stage
Any failure raises, so dag_00_master never reaches the staging cleanup (dag_04).

No double loads: when a push fails partway, staging is kept and the next run pushes again. A per-table
high-water mark (pipeline_control.push_watermark, the highest RAW_ID confirmed loaded) makes that retry
skip rows Snowflake already has. RAW_ID is the raw.fhir_bundles SERIAL, so it only ever grows.

Running totals: for every table confirmed loaded, the run records its row count, record count and sums in
pipeline_control.load_metrics, then ships unsent rows to SYNTHEA_PROD.PUBLIC.LOAD_METRICS through
LOAD_METRICS_PIPE. The dashboard sums that small table instead of scanning a billion rows.
pipeline_control lives outside flat/analytics on purpose: dag_04 truncates every table in those schemas.
"""
import base64
import hashlib
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pandas as pd
import psycopg2
import requests
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from airflow import DAG
from airflow.operators.python import PythonOperator

from pipeline_env import require_env, staging_db_config

CHUNK_SIZE = 250_000          # rows per Parquet file
LOAD_TIMEOUT_S = 600          # max wait for Snowpipe to report every file
POLL_EVERY_S = 10

CONTROL_SCHEMA = "pipeline_control"   # never under flat/analytics: dag_04 truncates those
METRICS_TABLE = "LOAD_METRICS"        # Snowflake table (and <name>_PIPE) the dashboard reads
# Tables whose record count / money the dashboard shows. Record ids are unique per bundle.
RECORD_ID = {
    "patients": "patient_id",
    "claims": "claim_id",
    "explanation_of_benefits": "eob_id",
    "encounters": "encounter_id",
    "procedures": "procedure_id",
}
AMOUNT = {"claims": "total_amount", "explanation_of_benefits": "payment_amount"}
METRIC_COLUMNS = [
    "run_tag", "table_name", "loaded_at", "row_count", "min_raw_id", "max_raw_id", "record_count",
    "amount_sum", "living_patients", "living_birth_days_sum", "deceased_lifespan_days_sum",
]
INT_METRICS = [
    "row_count", "min_raw_id", "max_raw_id", "record_count",
    "living_patients", "living_birth_days_sum", "deceased_lifespan_days_sum",
]


# --------------------------------------------------------------------------- settings
def snowflake_settings():
    """Every Snowflake setting comes from the pipeline .env (no defaults), read when the task runs."""
    database, schema, key_path, account, user, role = require_env(
        "SNOWFLAKE_TARGET_DB", "SNOWFLAKE_TARGET_SCHEMA", "SNOWFLAKE_DOCKER_PRIVATE_KEY_PATH",
        "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE",
    )
    return {
        "database": database,
        "schema": schema,
        "stage": f"{database}.{schema}.SNOWPIPE_STAGE",
        "key_path": os.path.expanduser(key_path),
        "account": account,
        "user": user,
        "role": role,
        # Optional override; otherwise derived from the account identifier.
        "host": os.environ.get("SNOWFLAKE_HOST") or f"{account.lower()}.snowflakecomputing.com",
    }


# --------------------------------------------------------------------------- auth
def load_private_key_obj(key_path):
    if not os.path.exists(key_path):
        raise RuntimeError(f"Snowpipe REST needs key-pair auth, but the private key file was not found at {key_path}.")
    with open(key_path, "rb") as key_file:
        return serialization.load_pem_private_key(key_file.read(), password=None, backend=default_backend())


def get_snowflake_config(sf, key_obj):
    # No warehouse: PUT and REMOVE need none, and Snowpipe loads are serverless.
    return {
        "user": sf["user"],
        "account": sf["account"],
        "role": sf["role"],
        "database": sf["database"],
        "schema": sf["schema"],
        "private_key": key_obj.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    }


class SnowpipeClient:
    """Minimal Snowpipe REST client (insertFiles / insertReport) using a key-pair JWT."""

    def __init__(self, sf, key_obj):
        self.host = sf["host"]
        self.account = sf["account"].split(".")[0].upper()
        self.user = sf["user"].upper()
        self.key = key_obj
        pub = key_obj.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(pub).digest()).decode()
        self._token, self._token_exp = None, datetime.min.replace(tzinfo=timezone.utc)

    def _jwt(self):
        now = datetime.now(timezone.utc)
        if self._token is None or now > self._token_exp - timedelta(minutes=5):
            self._token_exp = now + timedelta(minutes=59)
            self._token = jwt.encode(
                {"iss": f"{self.account}.{self.user}.{self.fingerprint}",
                 "sub": f"{self.account}.{self.user}", "iat": now, "exp": self._token_exp},
                self.key, algorithm="RS256",
            )
        return self._token

    def _call(self, method, path, **kw):
        headers = {
            "Authorization": f"Bearer {self._jwt()}",
            "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        url = f"https://{self.host}{path}{'&' if '?' in path else '?'}requestId={uuid.uuid4()}"
        r = requests.request(method, url, headers=headers, timeout=60, **kw)
        if r.status_code != 200:
            raise RuntimeError(f"Snowpipe REST {method} {path} -> HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    def insert_files(self, pipe, files):
        body = self._call("POST", f"/v1/data/pipes/{pipe}/insertFiles", json={"files": [{"path": f} for f in files]})
        if body.get("responseCode") != "SUCCESS":
            raise RuntimeError(f"insertFiles for {pipe} not accepted: {body}")

    def insert_report(self, pipe):
        return self._call("GET", f"/v1/data/pipes/{pipe}/insertReport").get("files", [])


# --------------------------------------------------------------------------- push
def stage_table(pg_conn, sf_cur, stage, table_name, run_tag, tmpdir, where=""):
    """Write one flat table (rows matching `where`) to Parquet files in the stage. Returns ({file: rows}, total_rows)."""
    folder = table_name.lower()
    files, total = {}, 0
    query = f"SELECT * FROM flat.{table_name} {where}"
    for i, chunk_df in enumerate(pd.read_sql(query, pg_conn, chunksize=CHUNK_SIZE)):
        if chunk_df.empty:
            continue
        # Snowflake columns are uppercase; the pipe matches columns by name (case-insensitive).
        chunk_df.columns = [c.upper() for c in chunk_df.columns]
        for col in chunk_df.columns:
            if chunk_df[col].apply(lambda x: isinstance(x, (dict, list))).any():
                chunk_df[col] = chunk_df[col].apply(lambda x: pd.io.json.dumps(x) if x is not None else None)
        chunk_df["DATA_SOURCE"] = "FHIR"

        fname = f"{run_tag}_{folder}_{i:04d}.parquet"
        local = os.path.join(tmpdir, fname)
        chunk_df.to_parquet(local, index=False)
        sf_cur.execute(f"PUT 'file://{local}' @{stage}/{folder}/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        status = sf_cur.fetchone()[6]
        os.remove(local)
        if status not in ("UPLOADED", "SKIPPED"):
            raise RuntimeError(f"PUT of {fname} returned {status}")
        files[fname] = len(chunk_df)
        total += len(chunk_df)
    return files, total


def wait_for_loads(client, pending):
    """pending: {pipe: {file: expected_rows}}. Wait until every file reports LOADED with that row count.

    Returns (errors, failed_pipes): a pipe is failed if any of its files failed, loaded a different row
    count, or was not reported before the timeout.
    """
    deadline = time.time() + LOAD_TIMEOUT_S
    errors, failed_pipes = [], set()
    while pending and time.time() < deadline:
        time.sleep(POLL_EVERY_S)
        for pipe in list(pending):
            for f in client.insert_report(pipe):
                path = f.get("path")
                if path not in pending[pipe]:
                    continue
                status = f.get("status")
                if status == "LOADED":
                    expected = pending[pipe].pop(path)
                    if f.get("rowsInserted") != expected:
                        errors.append(f"{pipe}/{path}: loaded {f.get('rowsInserted')} rows, expected {expected}")
                        failed_pipes.add(pipe)
                elif status in ("LOAD_FAILED", "PARTIALLY_LOADED"):
                    pending[pipe].pop(path)
                    errors.append(f"{pipe}/{path}: {status}: {f.get('firstError')}")
                    failed_pipes.add(pipe)
            if not pending[pipe]:
                del pending[pipe]
    if pending:
        waiting = sum(len(v) for v in pending.values())
        errors.append(f"timed out after {LOAD_TIMEOUT_S}s with {waiting} file(s) not reported loaded: {list(pending)}")
        failed_pipes.update(pending)
    return errors, failed_pipes


# --------------------------------------------------------------------------- watermarks + running totals
def ensure_control_tables(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {CONTROL_SCHEMA}")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {CONTROL_SCHEMA}.push_watermark (
                table_name text PRIMARY KEY,
                max_raw_id bigint NOT NULL,           -- highest RAW_ID confirmed loaded into Snowflake
                updated_at timestamptz NOT NULL DEFAULT now()
            )""")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {CONTROL_SCHEMA}.load_metrics (
                run_tag text NOT NULL,
                table_name text NOT NULL,
                loaded_at timestamptz NOT NULL DEFAULT now(),
                row_count bigint NOT NULL,
                min_raw_id bigint,
                max_raw_id bigint,
                record_count bigint,
                amount_sum numeric,
                living_patients bigint,
                living_birth_days_sum bigint,
                deceased_lifespan_days_sum bigint,
                sent_at timestamptz,                  -- set once the row is LOADED into Snowflake
                PRIMARY KEY (run_tag, table_name)
            )""")
    pg_conn.commit()


def read_watermarks(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute(f"SELECT table_name, max_raw_id FROM {CONTROL_SCHEMA}.push_watermark")
        return dict(cur.fetchall())


def has_raw_id(pg_conn, table_name):
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'flat' AND table_name = %s AND column_name = 'raw_id'""", (table_name,))
        return cur.fetchone() is not None


def batch_metrics(pg_conn, table_name, where):
    """Counts and sums for exactly the rows this run will push (same `where` as stage_table)."""
    rid, amt = RECORD_ID.get(table_name), AMOUNT.get(table_name)
    parts = [
        "count(*)", "min(raw_id)", "max(raw_id)",
        f"count(DISTINCT {rid})" if rid else "NULL::bigint",
        f"round(sum({amt}), 10)" if amt else "NULL::numeric",   # fits AMOUNT_SUM NUMBER(38,10)
    ]
    if table_name == "patients":
        # Patient-years = sum over patients of (death or today) - birth. "today" moves, so store the parts:
        # living count, living birth dates as day numbers, and finished lifespans in days.
        parts += [
            "count(*) FILTER (WHERE deceased_at IS NULL AND birth_date IS NOT NULL)",
            "sum(birth_date - DATE '1970-01-01') FILTER (WHERE deceased_at IS NULL)",
            "sum(deceased_at::date - birth_date) FILTER (WHERE deceased_at IS NOT NULL)",
        ]
    else:
        parts += ["NULL::bigint"] * 3
    with pg_conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(parts)} FROM flat.{table_name} {where}")
        return dict(zip(METRIC_COLUMNS[3:], cur.fetchone()))


def record_loads(pg_conn, run_tag, loaded):
    """loaded: {table: metrics}. Advance each table's watermark and queue its metrics row, in one transaction."""
    with pg_conn.cursor() as cur:
        for t, m in loaded.items():
            cur.execute(f"""
                INSERT INTO {CONTROL_SCHEMA}.push_watermark (table_name, max_raw_id) VALUES (%s, %s)
                ON CONFLICT (table_name) DO UPDATE
                SET max_raw_id = GREATEST(push_watermark.max_raw_id, EXCLUDED.max_raw_id), updated_at = now()""",
                (t, m["max_raw_id"]))
            cols = METRIC_COLUMNS[3:]
            cur.execute(f"""
                INSERT INTO {CONTROL_SCHEMA}.load_metrics (run_tag, table_name, {', '.join(cols)})
                VALUES (%s, %s, {', '.join(['%s'] * len(cols))})
                ON CONFLICT (run_tag, table_name) DO NOTHING""",
                (run_tag, t.upper(), *[m[c] for c in cols]))
    pg_conn.commit()


def ship_metrics(pg_conn, sf_cur, client, sf, run_tag, tmpdir):
    """Send every unsent load_metrics row (this run's and any a failed run left behind) to Snowflake.

    Returns a list of errors. Rows stay unsent on failure and go out with the next run. If Snowflake did load
    a file we then failed to confirm, the same (RUN_TAG, TABLE_NAME) can land twice; readers dedupe on it.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    df = pd.read_sql(
        f"SELECT {', '.join(METRIC_COLUMNS)} FROM {CONTROL_SCHEMA}.load_metrics "
        f"WHERE sent_at IS NULL ORDER BY loaded_at", pg_conn, coerce_float=False)  # keep exact Decimals
    if df.empty:
        return []
    for c in INT_METRICS:
        df[c] = df[c].astype("Int64")
    df["loaded_at"] = pd.to_datetime(df["loaded_at"], utc=True)
    df.columns = [c.upper() for c in df.columns]
    schema = pa.schema(
        [("RUN_TAG", pa.string()), ("TABLE_NAME", pa.string()), ("LOADED_AT", pa.timestamp("us", tz="UTC"))]
        + [(c.upper(), pa.int64()) for c in ["row_count", "min_raw_id", "max_raw_id", "record_count"]]
        + [("AMOUNT_SUM", pa.decimal128(38, 10))]
        + [(c.upper(), pa.int64()) for c in ["living_patients", "living_birth_days_sum", "deceased_lifespan_days_sum"]]
    )
    folder = METRICS_TABLE.lower()
    fname = f"{run_tag}_{folder}_{uuid.uuid4().hex[:6]}.parquet"
    local = os.path.join(tmpdir, fname)
    pq.write_table(pa.Table.from_pandas(df, schema=schema, preserve_index=False), local)
    sf_cur.execute(f"PUT 'file://{local}' @{sf['stage']}/{folder}/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
    status = sf_cur.fetchone()[6]
    os.remove(local)
    if status not in ("UPLOADED", "SKIPPED"):
        return [f"PUT of {fname} returned {status}"]

    pipe = f"{sf['database']}.{sf['schema']}.{METRICS_TABLE}_PIPE"
    client.insert_files(pipe, [fname])
    errors, _ = wait_for_loads(client, {pipe: {fname: len(df)}})
    if not errors:
        with pg_conn.cursor() as cur:
            cur.executemany(
                f"UPDATE {CONTROL_SCHEMA}.load_metrics SET sent_at = now() WHERE run_tag = %s AND table_name = %s",
                list(zip(df["RUN_TAG"], df["TABLE_NAME"])))
        pg_conn.commit()
        print(f"Shipped {len(df)} load_metrics row(s) to {METRICS_TABLE}")
    sf_cur.execute(f"REMOVE @{sf['stage']}/{folder}/ PATTERN = '.*{fname}.*'")
    return errors


def run_snowflake_push(**context):
    # Settings first: a missing one stops the task here, before anything is read or uploaded.
    sf = snowflake_settings()
    db_config = staging_db_config()
    run_tag = re.sub(r"[^0-9A-Za-z]+", "", context["run_id"])[-20:] + "_" + uuid.uuid4().hex[:6]
    key_obj = load_private_key_obj(sf["key_path"])
    client = SnowpipeClient(sf, key_obj)

    pg_conn = psycopg2.connect(**db_config)
    cursor = pg_conn.cursor()
    cursor.execute("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'flat'
          AND tablename NOT LIKE 'dbt_%'
          AND tablename <> 'base_synthea_entries';  -- intermediate model, not a final table
    """)
    tables = [r[0] for r in cursor.fetchall()]
    cursor.close()
    if not tables:
        pg_conn.close()
        # Fail closed: an empty flat schema means dbt produced nothing.
        raise RuntimeError("No tables found in flat schema to push. Failing so nothing downstream runs.")

    # Decide what each table still owes Snowflake, before anything is uploaded.
    ensure_control_tables(pg_conn)
    watermarks = read_watermarks(pg_conn)
    plan = {}  # table -> (where, metrics or None)
    for t in tables:
        if not has_raw_id(pg_conn, t):
            print(f"WARNING: flat.{t} has no raw_id; pushing every row with no retry guard or metrics")
            plan[t] = ("", None)
            continue
        wm = watermarks.get(t)
        if wm is not None:
            with pg_conn.cursor() as cur:
                cur.execute(f"SELECT max(raw_id) FROM flat.{t}")
                staged_max = cur.fetchone()[0]
            if staged_max is not None and staged_max < wm:
                pg_conn.close()
                # RAW_ID went backwards: raw.fhir_bundles was recreated or its sequence reset. Pushing nothing
                # silently would be worse than stopping.
                raise RuntimeError(
                    f"flat.{t} max raw_id {staged_max} is below its watermark {wm}. If staging was reset on "
                    f"purpose, clear {CONTROL_SCHEMA}.push_watermark and rerun.")
        where = f"WHERE raw_id > {int(wm)}" if wm is not None else ""
        metrics = batch_metrics(pg_conn, t, where)
        if metrics["row_count"] == 0:
            print(f"Skip flat.{t}: nothing above watermark {wm} (already loaded by an earlier run)")
            continue
        plan[t] = (where, metrics)

    sf_conn = snowflake.connector.connect(**get_snowflake_config(sf, key_obj))
    sf_cur = sf_conn.cursor()
    pending, totals, failed, pipe_of = {}, {}, [], {}
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            for t, (where, metrics) in plan.items():
                try:
                    files, total = stage_table(pg_conn, sf_cur, sf["stage"], t, run_tag, tmpdir, where)
                    totals[t] = total
                    if metrics is not None and total != metrics["row_count"]:
                        raise RuntimeError(f"staged {total} rows but counted {metrics['row_count']}")
                    if files:
                        pipe = f"{sf['database']}.{sf['schema']}.{t.upper()}_PIPE"
                        client.insert_files(pipe, list(files))
                        pending[pipe] = files
                        pipe_of[t] = pipe
                    print(f"Staged flat.{t}: {total} rows in {len(files)} file(s)")
                except Exception as e:
                    print(f"Failed staging flat.{t}: {e}")
                    failed.append(f"flat.{t}: {e}")

            submitted = {p: dict(f) for p, f in pending.items()}
            errors, failed_pipes = wait_for_loads(client, pending)
            failed.extend(errors)

            # Tables Snowflake confirmed: advance their watermarks and queue their metrics, even if other
            # tables failed, so a retry never loads them twice.
            loaded = {t: plan[t][1] for t, p in pipe_of.items() if p not in failed_pipes and plan[t][1] is not None}
            if loaded:
                record_loads(pg_conn, run_tag, loaded)
            failed.extend(ship_metrics(pg_conn, sf_cur, client, sf, run_tag, tmpdir))

        # Remove this run's files from the stage once Snowpipe has them (load history keeps dedupe).
        for pipe in submitted:
            folder = pipe.split(".")[-1][: -len("_PIPE")].lower()
            sf_cur.execute(f"REMOVE @{sf['stage']}/{folder}/ PATTERN = '.*{run_tag}.*'")
    finally:
        sf_cur.close()
        sf_conn.close()
        pg_conn.close()

    print(f"Snowpipe load summary: {sum(totals.values())} rows across {len(totals)} tables -> "
          f"{sf['database']}.{sf['schema']}")
    for t in sorted(totals):
        print(f"    {t}: {totals[t]}")

    # Fail loudly so the task goes red and dag_00 never reaches the cleanup DAG.
    if failed:
        raise RuntimeError(f"Snowpipe push had {len(failed)} problem(s): " + " | ".join(failed)[:3000])


default_args = {
    "owner": "airflow",
    "retries": 0,
    # A hung task (the 2026-11-20 Snowflake push sat "running" for two days and froze the every-5-minute
    # pipeline) now fails after 30 minutes, so the next scheduled run can start.
    "execution_timeout": timedelta(minutes=30),
}

with DAG(
    dag_id="dag_03_snowflake_push",
    default_args=default_args,
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["synthea", "snowflake", "fhir", "snowpipe"],
) as dag:

    # Cleanup (dag_04) is triggered by dag_00_master only, after this DAG succeeds.
    push = PythonOperator(
        task_id="push_to_snowflake",
        python_callable=run_snowflake_push,
    )
