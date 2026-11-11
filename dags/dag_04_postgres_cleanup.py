"""
DAG 4: Safely clean up local Postgres staging tables (raw.fhir_bundles and analytics.*)
now that data has been successfully pushed to Snowflake.

Before issuing any TRUNCATE, this DAG checks that the most recent dag_03_snowflake_push
run finished in the 'success' state. It fails closed: no dag_03 run, or a non-success run,
aborts the cleanup. (dag_03 raises on any failed table, so success means every table pushed.)
"""
import os
import psycopg2
from datetime import datetime

from airflow import DAG
from airflow.models import DagRun
from airflow.operators.python import PythonOperator
from airflow.utils.state import DagRunState

DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", "staging_db"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "host.docker.internal"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}


def delete_processed_and_clean_staging(**context):
    # Guard: the latest dag_03 run must exist and have succeeded (fail closed).
    # An XCom pull across DAG runs does not work (XComs are scoped to a run), so
    # check the run state directly.
    runs = DagRun.find(dag_id="dag_03_snowflake_push")
    if not runs:
        raise RuntimeError("Aborting cleanup: no dag_03_snowflake_push run found.")
    latest = max(runs, key=lambda r: r.execution_date)
    if latest.state != DagRunState.SUCCESS:
        raise RuntimeError(
            f"Aborting cleanup: latest dag_03 run ({latest.run_id}) is in state '{latest.state}', not success."
        )

    failures = []
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 1. Clean up raw FHIR bundles landing table
    try:
        cursor.execute("TRUNCATE TABLE raw.fhir_bundles;")
        conn.commit()
        print("Successfully truncated raw.fhir_bundles (confirmed pushed to Snowflake).")
    except Exception as e:
        conn.rollback()
        print(f"Could not truncate raw.fhir_bundles: {e}")
        failures.append("raw.fhir_bundles")

    # 2. Clean up downstream analytics/flat schemas to maintain zero-growth local footprint
    cursor.execute("""
        SELECT schemaname, tablename 
        FROM pg_tables 
        WHERE schemaname IN ('analytics', 'flat')
          AND tablename NOT LIKE 'dbt_%';
    """)
    tables = cursor.fetchall()

    for schema_name, table_name in tables:
        try:
            cursor.execute(f"TRUNCATE TABLE {schema_name}.{table_name};")
            conn.commit()
            print(f"Truncated {schema_name}.{table_name}")
        except Exception as e:
            conn.rollback()
            print(f"Failed to truncate {schema_name}.{table_name}: {e}")
            failures.append(f"{schema_name}.{table_name}")

    cursor.close()
    conn.close()

    if failures:
        raise RuntimeError(f"Cleanup incomplete, could not truncate: {', '.join(failures)}")


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
    tags=["synthea", "cleanup", "fhir"],
) as dag:

    cleanup = PythonOperator(
        task_id="delete_processed_and_clean_staging",
        python_callable=delete_processed_and_clean_staging,
    )
