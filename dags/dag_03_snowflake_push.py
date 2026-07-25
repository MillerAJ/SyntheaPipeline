"""
DAG 3: Push every flat.* table from Postgres to Snowflake, append-only.

Chunked read (never loads a full table into memory — flat.observations
alone runs into the hundreds of millions of rows) and append-only write
(never drops/replaces the Snowflake table). Re-running this against the
same Postgres data WILL duplicate rows in Snowflake — that's why dag_04's
Postgres truncate only fires after a confirmed successful push, so the
same raw/flat data is never pushed twice.

Pushes an XCom flag ('push_succeeded') that dag_04_postgres_cleanup checks
before truncating anything — a failed push should never be followed by
a truncate, or data is gone from both places.
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
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.operators.empty import EmptyOperator
from datetime import datetime

load_dotenv()

CHUNK_SIZE = 100_000  # rows per chunk — lower if the container is memory-constrained

DB_CONFIG = {
    "dbname": "staging_db",
    "user": "postgres",
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": "host.docker.internal",
    "port": "5432",
}

KEY_FILE_PATH = os.path.expanduser(os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH", "~/.snowflake/rsa_key.p8"))


def load_private_key():
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
    return {
        "user": os.getenv("SNOWFLAKE_USER"),
        "private_key": load_private_key(),
        "password": os.getenv("SNOWFLAKE_PASSWORD"),
        "account": os.getenv("SNOWFLAKE_ACCOUNT"),
        "role": os.getenv("SNOWFLAKE_ROLE"),
        "warehouse": os.getenv("SNOWFLAKE_WH"),
        "database": os.getenv("SNOWFLAKE_DB"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA"),
    }


def push_table(pg_conn, sf_conn, table_name):
    """Chunked read from Postgres, append-only chunked write to Snowflake."""
    snowflake_table_name = table_name.upper()
    total_rows = 0

    for chunk_df in pd.read_sql(
        f"SELECT * FROM flat.{table_name}", pg_conn, chunksize=CHUNK_SIZE
    ):
        write_pandas(
            sf_conn,
            chunk_df,
            snowflake_table_name,
            auto_create_table=True,
            overwrite=False,        # append-only — never drops/replaces the Snowflake table
            use_logical_type=True,  # fixes tz-aware datetime columns writing incorrectly
        )
        total_rows += len(chunk_df)
        print(f"      ...{table_name}: {total_rows} rows so far")

    return total_rows


def run_snowflake_push(**context):
    pg_conn = psycopg2.connect(**DB_CONFIG)
    sf_conn = snowflake.connector.connect(**get_snowflake_config())

    cursor = pg_conn.cursor()
    cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'flat';")
    tables = [row[0] for row in cursor.fetchall()]
    cursor.close()

    all_succeeded = True
    for table_name in tables:
        try:
            nrows = push_table(pg_conn, sf_conn, table_name)
            print(f"✅ {table_name}: {nrows} rows")
        except Exception as e:
            print(f"❌ {table_name} failed: {e}")
            all_succeeded = False

    pg_conn.close()
    sf_conn.close()

    context["ti"].xcom_push(key="push_succeeded", value=all_succeeded)
    return "trigger_cleanup" if all_succeeded else "skip_cleanup"


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
    tags=["synthea", "snowflake"],
) as dag:

    push = BranchPythonOperator(
        task_id="push_to_snowflake",
        python_callable=run_snowflake_push,
    )

    trigger_cleanup = TriggerDagRunOperator(
        task_id="trigger_cleanup",
        trigger_dag_id="dag_04_postgres_cleanup",
    )

    skip_cleanup = EmptyOperator(task_id="skip_cleanup")

    push >> [trigger_cleanup, skip_cleanup]
