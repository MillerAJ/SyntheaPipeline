from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 0,
}

with DAG(
    dag_id="dag_00_master",
    default_args=default_args,
    description="Orchestrates full Synthea pipeline DAGs 01 through 04 sequentially",
    schedule_interval="*/5 * * * *",  # every 5 minutes: Snowpipe makes small, frequent loads cheap
    catchup=False,
    max_active_runs=1,
) as dag:

    trigger_dag_01 = TriggerDagRunOperator(
        task_id="trigger_dag_01_generate_and_load",
        trigger_dag_id="dag_01_generate_and_load",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True,
    )

    trigger_dag_02 = TriggerDagRunOperator(
        task_id="trigger_dag_02_dbt_transform",
        trigger_dag_id="dag_02_dbt_transform",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True,
    )

    trigger_dag_03 = TriggerDagRunOperator(
        task_id="trigger_dag_03_snowflake_push",
        trigger_dag_id="dag_03_snowflake_push",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True,
    )

    trigger_dag_04 = TriggerDagRunOperator(
        task_id="trigger_dag_04_postgres_cleanup",
        trigger_dag_id="dag_04_postgres_cleanup",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True,
    )

    # Set linear dependency chain
    trigger_dag_01 >> trigger_dag_02 >> trigger_dag_03 >> trigger_dag_04
