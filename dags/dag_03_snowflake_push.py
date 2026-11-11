"""
DAG 3: Push Postgres tables (raw, analytics, flat) to Snowflake's RAW schema, append-only.
"""
import os
import pandas as pd
import psycopg2
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

load_dotenv()

CHUNK_SIZE = 1_000_000

# Landing zone: a schema with no pre-existing tables, so write_pandas(auto_create_table=True)
# creates each table from the DataFrame's own columns. Override via env if needed.
SF_TARGET_DATABASE = os.getenv("SNOWFLAKE_TARGET_DB", "SYNTHEA_PROD")
SF_TARGET_SCHEMA = os.getenv("SNOWFLAKE_TARGET_SCHEMA", "PUBLIC")

DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", "staging_db"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "host.docker.internal"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

KEY_FILE_PATH = os.path.expanduser(os.getenv("SNOWFLAKE_DOCKER_PRIVATE_KEY_PATH", "~/.snowflake/rsa_key.p8"))


def load_private_key():
    if not os.path.exists(KEY_FILE_PATH):
        return None
    with open(KEY_FILE_PATH, "rb") as key_file:
        p_key = serialization.load_pem_private_key(
            key_file.read(), password=None, backend=default_backend()
        )
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_snowflake_config():
    p_key = load_private_key()
    config = {
        "user": os.getenv("SNOWFLAKE_USER"),
        "account": os.getenv("SNOWFLAKE_ACCOUNT"),
        "role": os.getenv("SNOWFLAKE_ROLE"),
        "warehouse": os.getenv("SNOWFLAKE_WH"),
        "database": os.getenv("SNOWFLAKE_DB"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA", "RAW"),
    }
    if p_key:
        config["private_key"] = p_key
    else:
        config["password"] = os.getenv("SNOWFLAKE_PASSWORD")
    return config

def push_table(pg_conn, sf_conn, schema_name, table_name):
    """Chunked read from Postgres schema, append-only chunked write to Snowflake RAW schema."""
    snowflake_table_name = table_name.upper()
    total_rows = 0

    query = f"SELECT * FROM {schema_name}.{table_name}"

    for chunk_df in pd.read_sql(query, pg_conn, chunksize=CHUNK_SIZE):
        # Snowflake tables use unquoted (uppercase) identifiers; write_pandas quotes column
        # names exactly, so the DataFrame columns must be uppercase to match.
        chunk_df.columns = [c.upper() for c in chunk_df.columns]
        for col in chunk_df.columns:
            if chunk_df[col].apply(lambda x: isinstance(x, (dict, list))).any():
                chunk_df[col] = chunk_df[col].apply(lambda x: pd.io.json.dumps(x) if x is not None else None)

        write_pandas(
            sf_conn,
            chunk_df,
            snowflake_table_name,
            database=SF_TARGET_DATABASE,
            schema=SF_TARGET_SCHEMA,
            auto_create_table=True,
            overwrite=False,
            use_logical_type=True,
            parallel=8,
            chunk_size=100_000,
        )
        total_rows += len(chunk_df)
        print(f"    ...{schema_name}.{table_name} -> {SF_TARGET_SCHEMA}.{snowflake_table_name}: {total_rows} rows pushed")

    return total_rows

def run_snowflake_push(**context):
    pg_conn = psycopg2.connect(**DB_CONFIG)
    sf_conn = snowflake.connector.connect(**get_snowflake_config())

    cursor = pg_conn.cursor()

    cursor.execute("""
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname = 'flat'
          AND tablename NOT LIKE 'dbt_%'
          AND tablename <> 'base_synthea_entries';  -- intermediate model, not a final table
    """)
    target_tables = cursor.fetchall()
    cursor.close()

    if not target_tables:
        pg_conn.close()
        sf_conn.close()
        # Fail closed: an empty flat schema means dbt produced nothing, and the
        # downstream cleanup DAG would otherwise wipe the raw staging data.
        raise RuntimeError("No tables found in flat schema to push. Failing so nothing downstream runs.")

    failed = []
    for schema_name, table_name in target_tables:
        try:
            nrows = push_table(pg_conn, sf_conn, schema_name, table_name)
            print(f"Pushed {schema_name}.{table_name} ({nrows} rows) to {SF_TARGET_DATABASE}.{SF_TARGET_SCHEMA}")
        except Exception as e:
            print(f"Failed pushing {schema_name}.{table_name}: {e}")
            failed.append(f"{schema_name}.{table_name}")

    pg_conn.close()
    sf_conn.close()

    # Fail loudly so the task goes red and dag_00 never reaches the cleanup DAG.
    if failed:
        raise RuntimeError(
            f"Snowflake push failed for {len(failed)}/{len(target_tables)} tables: {', '.join(failed)}"
        )


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
    tags=["synthea", "snowflake", "fhir"],
) as dag:

    # Cleanup (dag_04) is triggered by dag_00_master only, after this DAG succeeds.
    push = PythonOperator(
        task_id="push_to_snowflake",
        python_callable=run_snowflake_push,
    )

