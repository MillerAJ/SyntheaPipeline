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
from datetime import datetime
from urllib.parse import quote_plus

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DB_USER = os.getenv("POSTGRES_USER", "airflow")
DB_PASSWORD = os.getenv("STAGING_DB_PASSWORD")  # set in .env; checked at task runtime
DB_HOST = os.getenv("POSTGRES_HOST", "airflow-metadata-db")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "staging_db")


# Directories & Execution Params
SYNTHEA_DIR = os.getenv("SYNTHEA_DIR", "/opt/airflow/synthea")
OUTPUT_DIR = os.path.join(SYNTHEA_DIR, "fhir")
NUM_PATIENTS = int(os.getenv("SYNTHEA_PATIENTS", "100"))


def generate_and_load_fhir():
    if not DB_PASSWORD:
        raise RuntimeError("STAGING_DB_PASSWORD is not set. Add it to the pipeline .env and recreate the Airflow containers.")
    engine = create_engine(
        f"postgresql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
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
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if os.path.exists(OUTPUT_DIR):
        for f in glob.glob(f"{OUTPUT_DIR}/*.json"):
            os.remove(f)

    # 4. Execute Synthea Java CLI
    synthea_jar = glob.glob(f"{SYNTHEA_DIR}/synthea-with-dependencies*.jar")
    if not synthea_jar:
        raise FileNotFoundError(f"Could not locate Synthea JAR in {SYNTHEA_DIR}")

    cmd = [
        "java",
        "-jar",
        synthea_jar[0],
        "-p",
        str(NUM_PATIENTS),
        "--exporter.fhir.export=true",
        "--exporter.hospital.fhir.export=false",
        "--exporter.practitioner.fhir.export=false",
        f"--exporter.baseDirectory={SYNTHEA_DIR}",
        "New York",
    ]

    print(f"Executing Synthea command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    # 5. Ingest JSON bundles into Postgres raw.fhir_bundles
    json_files = glob.glob(os.path.join(OUTPUT_DIR, "*.json"))
    print(f"Discovered {len(json_files)} FHIR JSON bundles to ingest.")

    if not json_files:
        raise ValueError(f"No JSON bundle files found in directory: {OUTPUT_DIR}. Aborting run.")


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



