"""
DAG 4: Truncate all Postgres tables (raw + flat) now that everything has
been pushed to Snowflake. Only ever triggered by dag_03_snowflake_push
after a fully successful push — see dag_03's branch logic.
"""
import os
import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

DB_CONFIG = {
    "dbname": "staging_db",
    "user": "postgres",
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": "host.docker.internal",
    "port": "5432",
}


def truncate_all():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    for schema in ("raw", "flat"):
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s;", (schema,))
        tables = [row[0] for row in cursor.fetchall()]
        for table_name in tables:
            try:
                cursor.execute(f"TRUNCATE TABLE {schema}.{table_name};")
                conn.commit()
                print(f"🧹 Truncated {schema}.{table_name}")
            except Exception as e:
                conn.rollback()
                print(f"❌ Failed to truncate {schema}.{table_name}: {e}")

    cursor.close()
    conn.close()


default_args = {
    "owner": "airflow",
    "retries": 0,
}

with DAG(
    dag_id="dag_04_postgres_cleanup",
    default_args=default_args,
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["synthea", "cleanup"],
) as dag:

    cleanup = PythonOperator(
        task_id="truncate_raw_and_flat",
        python_callable=truncate_all,
    )
