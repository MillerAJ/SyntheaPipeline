"""
DAG 1: Generate Synthea FHIR R4 JSON bundles and load them into PostgreSQL.

Generates patient clinical data via the Synthea Java CLI executable into JSON bundles,
staged locally, and ingests them into raw.fhir_bundles (JSONB column) using SQLAlchemy.
"""
import glob
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine, text

from pipeline_env import require_env, staging_db_config


def generate_and_load_fhir():
    # Every setting comes from the pipeline .env (no defaults); a missing one stops here, before any work.
    db = staging_db_config()
    synthea_dir, num_patients = require_env("SYNTHEA_DIR", "SYNTHEA_PATIENTS")
    num_patients = int(num_patients)
    output_dir = os.path.join(synthea_dir, "fhir")

    engine = create_engine(
        f"postgresql://{quote_plus(db['user'])}:{quote_plus(db['password'])}@{db['host']}:{db['port']}/{db['dbname']}"
    )

    # 1. Ensure landing schema and target JSONB table exist with an explicit unique constraint
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw;"))
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS raw.fhir_bundles (
                id SERIAL PRIMARY KEY,
                file_name VARCHAR(255) NOT NULL,
                payload JSONB NOT NULL,
                loaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_fhir_file_name UNIQUE (file_name)
            );
        """
            )
        )

    # 2. Check disk space before kicking off generation
    stat = shutil.disk_usage("/")
    free_gb = stat.free / (1024**3)
    print(f"{free_gb:.2f} GB free disk space available.")
    if free_gb < 1.0:
        raise RuntimeError(f"Insufficient disk space ({free_gb:.2f} GB available). Aborting run.")

    # 3. Ensure output directory exists and clean up stale FHIR output files if present
    os.makedirs(output_dir, exist_ok=True)
    if os.path.exists(output_dir):
        for f in glob.glob(f"{output_dir}/*.json"):
            os.remove(f)

    # 4. Execute Synthea Java CLI
    synthea_jar = glob.glob(f"{synthea_dir}/synthea-with-dependencies*.jar")
    if not synthea_jar:
        raise FileNotFoundError(f"Could not locate Synthea JAR in {synthea_dir}")

    cmd = [
        "java",
        "-jar",
        synthea_jar[0],
        "-p",
        str(num_patients),
        "--exporter.fhir.export=true",
        "--exporter.hospital.fhir.export=false",
        "--exporter.practitioner.fhir.export=false",
        f"--exporter.baseDirectory={synthea_dir}",
        "New York",
    ]

    print(f"Executing Synthea command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    # 5. Ingest JSON bundles into Postgres raw.fhir_bundles
    json_files = glob.glob(os.path.join(output_dir, "*.json"))
    print(f"Discovered {len(json_files)} FHIR JSON bundles to ingest.")

    if not json_files:
        raise ValueError(f"No JSON bundle files found in directory: {output_dir}. Aborting run.")


    records = []
    for file_path in json_files:
        file_name = os.path.basename(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            records.append({"file_name": file_name, "payload": json.dumps(data)})

    # insert_sql = text(
    #     """
    #     INSERT INTO raw.fhir_bundles (file_name, payload)
    #     VALUES (:file_name, :payload::jsonb)
    # """
    # )

    insert_sql = text("""
        INSERT INTO raw.fhir_bundles (file_name, payload)
        VALUES (:file_name, CAST(:payload AS jsonb))
        ON CONFLICT (file_name) DO UPDATE 
        SET payload = EXCLUDED.payload, loaded_at = CURRENT_TIMESTAMP
    """)

    with engine.begin() as conn:
        conn.execute(insert_sql, records)

    print(f"Successfully ingested {len(records)} bundles into raw.fhir_bundles.")

    # 6. Cleanup local temporary FHIR files safely
    for file_path in json_files:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Could not remove temporary file {file_path}: {e}")
            
    print("Temporary FHIR JSON output files cleaned up.")


default_args = {
    "owner": "airflow",
    "retries": 0,
    # A hung task (the 2026-11-20 Snowflake push sat "running" for two days and froze the every-5-minute
    # pipeline) now fails after 30 minutes, so the next scheduled run can start.
    "execution_timeout": timedelta(minutes=30),
}

with DAG(
    dag_id="dag_01_generate_and_load",
    default_args=default_args,
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["synthea", "fhir", "postgres"],
) as dag:

    generate_and_load_task = PythonOperator(
        task_id="generate_and_load_all_batches",
        python_callable=generate_and_load_fhir,
    )



