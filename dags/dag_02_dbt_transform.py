"""
DAG 2: Run dbt against Postgres to flatten raw.raw_synthea into flat.* tables.

Uses `dbt-ol` (the openlineage-dbt wrapper) instead of the plain `dbt`
command — it runs dbt normally but also emits lineage events to Marquez
for every model, picking up column-level lineage where dbt supports it.
"""
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from datetime import datetime

DBT_PROJECT_DIR = "/opt/airflow/dbt_synthea"

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
    tags=["synthea", "dbt"],
) as dag:

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            f"OPENLINEAGE_URL=http://marquez:5000 "
            f"OPENLINEAGE_NAMESPACE=synthea_pipeline "
            f"dbt-ol run --profiles-dir {DBT_PROJECT_DIR}"
        ),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            f"dbt test --profiles-dir {DBT_PROJECT_DIR}"
        ),
    )

    trigger_snowflake_push = TriggerDagRunOperator(
        task_id="trigger_snowflake_push",
        trigger_dag_id="dag_03_snowflake_push",
    )

    dbt_run >> dbt_test >> trigger_snowflake_push
