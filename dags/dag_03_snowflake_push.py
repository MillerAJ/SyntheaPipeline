"""
DAG 3: Push the flat Postgres tables to Snowflake SYNTHEA_PROD.PUBLIC through Snowpipe.

Snowpipe is serverless (billed per GB loaded), so this DAG never wakes a warehouse:
  1. each flat table is written to Parquet files and PUT to @SNOWPIPE_STAGE/<table>/
  2. the table's pipe (<TABLE>_PIPE) is notified through the Snowpipe REST API (key-pair JWT)
  3. the DAG waits until every file reports LOADED with the expected row count, then
     removes the loaded files from the stage
Any failure raises, so dag_00_master never reaches the staging cleanup (dag_04).
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
def stage_table(pg_conn, sf_cur, stage, table_name, run_tag, tmpdir):
    """Write one flat table to Parquet files in the stage. Returns ({file: rows}, total_rows)."""
    folder = table_name.lower()
    files, total = {}, 0
    query = f"SELECT * FROM flat.{table_name}"
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
    """pending: {pipe: {file: expected_rows}}. Raise unless every file reports LOADED with that row count."""
    deadline = time.time() + LOAD_TIMEOUT_S
    errors = []
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
                elif status in ("LOAD_FAILED", "PARTIALLY_LOADED"):
                    pending[pipe].pop(path)
                    errors.append(f"{pipe}/{path}: {status}: {f.get('firstError')}")
            if not pending[pipe]:
                del pending[pipe]
    if pending:
        waiting = sum(len(v) for v in pending.values())
        errors.append(f"timed out after {LOAD_TIMEOUT_S}s with {waiting} file(s) not reported loaded: {list(pending)}")
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

    sf_conn = snowflake.connector.connect(**get_snowflake_config(sf, key_obj))
    sf_cur = sf_conn.cursor()
    pending, totals, failed = {}, {}, []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            for t in tables:
                try:
                    files, total = stage_table(pg_conn, sf_cur, sf["stage"], t, run_tag, tmpdir)
                    totals[t] = total
                    if files:
                        pipe = f"{sf['database']}.{sf['schema']}.{t.upper()}_PIPE"
                        client.insert_files(pipe, list(files))
                        pending[pipe] = files
                    print(f"Staged flat.{t}: {total} rows in {len(files)} file(s)")
                except Exception as e:
                    print(f"Failed staging flat.{t}: {e}")
                    failed.append(f"flat.{t}: {e}")

        submitted = {p: dict(f) for p, f in pending.items()}
        errors = wait_for_loads(client, pending)
        failed.extend(errors)

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
