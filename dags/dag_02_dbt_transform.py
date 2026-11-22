"""
DAG 2: Run dbt against Postgres to parse raw FHIR R4 JSON bundles (raw.fhir_bundles)
into flat per-resource tables in the `flat` schema (patients, encounters, observations, ...).

dbt is installed into an isolated virtualenv (DBT_VENV_DIR) to avoid
dependency conflicts with Airflow's core Python environment.

Lineage metadata is automatically emitted to Marquez via openlineage-dbt (dbt-ol).

Settings come from the pipeline .env with no defaults. Each task checks its own settings first and stops
before doing anything if one is missing. dbt's profiles.yml reads the STAGING_DB_* settings itself.
"""
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

STAGING_DB = ["STAGING_DB_HOST", "STAGING_DB_PORT", "STAGING_DB_NAME", "STAGING_DB_USER", "STAGING_DB_PASSWORD"]


def require(*names):
    """Bash prelude: stop the task with a clear message if any named setting is missing or empty."""
    return (
        f"for v in {' '.join(names)}; do "
        '[ -n "${!v}" ] || { echo "Missing required setting: $v. Add it to the pipeline .env and recreate '
        'the containers (docker compose up -d)."; exit 1; }; done; '
    )


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
            require("DBT_VENV_DIR")
            + 'if [ ! -f "$DBT_VENV_DIR/bin/dbt" ]; then '
            + '  python3 -m venv "$DBT_VENV_DIR" && '
            + '  "$DBT_VENV_DIR/bin/pip" install --quiet --upgrade pip && '
            + '  "$DBT_VENV_DIR/bin/pip" install --quiet dbt-postgres openlineage-dbt; '
            + "else "
            + "  echo 'dbt venv already exists, skipping install'; "
            + "fi"
        ),
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            require("DBT_PROJECT_DIR", "DBT_VENV_DIR", "MARQUEZ_URL", *STAGING_DB)
            + 'cd "$DBT_PROJECT_DIR" && '
            + 'export PATH="$DBT_VENV_DIR/bin:$PATH" && '
            + 'OPENLINEAGE_URL="$MARQUEZ_URL" '
            + "OPENLINEAGE_NAMESPACE=synthea_pipeline "
            + 'dbt-ol run --profiles-dir "$DBT_PROJECT_DIR"'
        ),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            require("DBT_PROJECT_DIR", "DBT_VENV_DIR", *STAGING_DB)
            + 'cd "$DBT_PROJECT_DIR" && '
            + 'export PATH="$DBT_VENV_DIR/bin:$PATH" && '
            + 'dbt test --profiles-dir "$DBT_PROJECT_DIR"'
        ),
    )

    setup_dbt_venv >> dbt_run >> dbt_test
