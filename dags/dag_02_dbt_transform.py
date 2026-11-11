"""
DAG 2: Run dbt against Postgres to parse raw FHIR R4 JSON bundles (raw.fhir_bundles)
into flat per-resource tables in the `flat` schema (patients, encounters, observations, ...).

dbt is installed into an isolated virtualenv (/opt/airflow/dbt_venv) to avoid
dependency conflicts with Airflow's core Python environment.

Lineage metadata is automatically emitted to Marquez via openlineage-dbt (dbt-ol).
"""
import os
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

DBT_PROJECT_DIR = os.getenv("DBT_PROJECT_DIR", "/opt/airflow/dbt_synthea")
DBT_VENV_DIR = os.getenv("DBT_VENV_DIR", "/opt/airflow/dbt_venv")
MARQUEZ_URL = os.getenv("MARQUEZ_URL", "http://marquez:8080")

default_args = {
    "owner": "airflow",
    "retries": 0,
}

with DAG(
    dag_id="dag_02_dbt_transform",
    default_args=default_args,
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["synthea", "dbt", "fhir", "json"],
) as dag:

    setup_dbt_venv = BashOperator(
        task_id="setup_dbt_venv",
        bash_command=(
            f"if [ ! -f {DBT_VENV_DIR}/bin/dbt ]; then "
            f"  python3 -m venv {DBT_VENV_DIR} && "
            f"  {DBT_VENV_DIR}/bin/pip install --quiet --upgrade pip && "
            f"  {DBT_VENV_DIR}/bin/pip install --quiet dbt-postgres openlineage-dbt; "
            f"else "
            f"  echo 'dbt venv already exists, skipping install'; "
            f"fi"
        ),
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            f"export PATH={DBT_VENV_DIR}/bin:$PATH && "
            f"OPENLINEAGE_URL={MARQUEZ_URL} "
            f"OPENLINEAGE_NAMESPACE=synthea_pipeline "
            f"dbt-ol run --profiles-dir {DBT_PROJECT_DIR}"
        ),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            f"export PATH={DBT_VENV_DIR}/bin:$PATH && "
            f"dbt test --profiles-dir {DBT_PROJECT_DIR}"
        ),
    )

    setup_dbt_venv >> dbt_run >> dbt_test




    
