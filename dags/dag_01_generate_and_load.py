"""
DAG 1: Generate Synthea data and load it into Postgres raw.raw_synthea.

Runs the batch loop (generate -> consolidate/gzip -> Postgres insert) for
every batch, then triggers dag_02_dbt_transform once all batches are loaded.
"""
import os
import shutil
import subprocess
import sys
import glob
import json
import gzip

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from datetime import datetime

import psycopg2
from psycopg2 import extras

SYNTHEA_DIR = os.path.expanduser("~/synthea")
FHIR_DIR = os.path.join(SYNTHEA_DIR, "output", "fhir")
OUTPUT_DIR = os.path.join(SYNTHEA_DIR, "output")
JAR_NAME = "synthea-with-dependencies.jar"
SYNTHEA_JAR_PATH = os.path.join(SYNTHEA_DIR, "build", "libs", JAR_NAME)

TOTAL_POPULATION = 200000
BATCH_SIZE = 10000
POSTGRES_BATCH_SIZE = 1000
STATE = "New York"
THREADS = 12

DB_CONFIG = {
    "dbname": "staging_db",
    "user": "postgres",
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": "host.docker.internal",  # containers reach host Postgres via this
    "port": "5432",
}


def check_disk_space(min_free_gb=20):
    total, used, free = shutil.disk_usage("/")
    free_gb = free / (1024 ** 3)
    if free_gb < min_free_gb:
        raise RuntimeError(f"Only {free_gb:.1f} GB free — aborting before it gets worse.")
    print(f"💾 {free_gb:.1f} GB free — OK to proceed.")


def clean_output_directory():
    print("🧹 Cleaning local FHIR output directory...")
    if os.path.exists(FHIR_DIR):
        for filename in os.listdir(FHIR_DIR):
            file_path = os.path.join(FHIR_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")
    else:
        os.makedirs(FHIR_DIR, exist_ok=True)


def run_synthea_generation(batch_size):
    cmd = [
        "java", "-Xms16g", "-Xmx48g",
        "-jar", SYNTHEA_JAR_PATH,
        "-p", str(batch_size),
        "-t", str(THREADS),
        STATE,
    ]
    subprocess.run(cmd, cwd=SYNTHEA_DIR, check=True)


def consolidate_and_compress(batch_num):
    compressed_file_path = os.path.join(OUTPUT_DIR, f"ny_patients_batch_{batch_num}.json.gz")
    json_files = glob.glob(os.path.join(FHIR_DIR, "*.json"))
    if not json_files:
        return None

    with gzip.open(compressed_file_path, "wt", encoding="utf-8") as f_out:
        for file_path in json_files:
            if "hospitalInformation" in file_path or "practitionerInformation" in file_path:
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f_in:
                    record = json.load(f_in)
                    f_out.write(json.dumps(record) + "\n")
            except Exception as e:
                print(f"⚠️ Error processing file {file_path}: {e}")

    return compressed_file_path


def trigger_postgres_upload(compressed_file_path):
    if not compressed_file_path or not os.path.exists(compressed_file_path):
        return

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    insert_query = "INSERT INTO raw.raw_synthea (payload) VALUES %s"
    batch_data = []
    uploaded_count = 0

    with gzip.open(compressed_file_path, "rt", encoding="utf-8") as f_in:
        for line in f_in:
            clean_line = line.strip()
            if not clean_line:
                continue
            json_str = json.dumps(json.loads(clean_line), ensure_ascii=True)
            batch_data.append((json_str,))
            if len(batch_data) >= POSTGRES_BATCH_SIZE:
                extras.execute_values(cursor, insert_query, batch_data)
                conn.commit()
                uploaded_count += len(batch_data)
                batch_data = []
        if batch_data:
            extras.execute_values(cursor, insert_query, batch_data)
            conn.commit()
            uploaded_count += len(batch_data)

    print(f"✅ Loaded {uploaded_count} records.")
    cursor.close()
    conn.close()
    os.remove(compressed_file_path)


def run_all_batches():
    total_batches = (TOTAL_POPULATION + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(1, total_batches + 1):
        print(f"--- Batch {i} of {total_batches} ---")
        check_disk_space()
        clean_output_directory()
        run_synthea_generation(batch_size=BATCH_SIZE)
        compressed_path = consolidate_and_compress(batch_num=i)
        clean_output_directory()
        trigger_postgres_upload(compressed_path)


default_args = {
    "owner": "airflow",
    "retries": 0,
}

with DAG(
    dag_id="dag_01_generate_and_load",
    default_args=default_args,
    schedule=None,  # triggered manually or externally, not on a fixed schedule
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["synthea", "generate"],
) as dag:

    generate_and_load = PythonOperator(
        task_id="generate_and_load_all_batches",
        python_callable=run_all_batches,
    )

    trigger_dbt = TriggerDagRunOperator(
        task_id="trigger_dbt_transform",
        trigger_dag_id="dag_02_dbt_transform",
    )

    generate_and_load >> trigger_dbt
