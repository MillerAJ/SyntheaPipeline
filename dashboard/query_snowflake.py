import json
import os
import snowflake.connector
import toml
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

# Every number on the dashboard comes from LOAD_METRICS: one small row per (pipeline run, table) that the
# pipeline (dag_03) writes after Snowflake confirms the load, plus hourly backfill rows for older history.
# Summing it is a scan of a few thousand rows instead of the ~1 billion in the data tables.
# The same (RUN_TAG, TABLE_NAME) can land twice in a rare retry, so every query dedupes on it first.
METRICS_CTE = """
    WITH m AS (
        SELECT * FROM SYNTHEA_PROD.PUBLIC.LOAD_METRICS
        QUALIFY ROW_NUMBER() OVER (PARTITION BY RUN_TAG, TABLE_NAME ORDER BY LOADED_AT) = 1
    )
"""


def fetch_and_cache_metrics():
    # 1. Load Snowflake secrets
    secrets = toml.load(".streamlit/secrets.toml")["snowflake"]

    # 2. Key loading
    key_path = os.path.expanduser(secrets["private_key_path"])
    passphrase = secrets.get("private_key_passphrase")
    passphrase_bytes = passphrase.encode("utf-8") if passphrase else None

    with open(key_path, "rb") as key_file:
        p_key = serialization.load_pem_private_key(
            key_file.read(),
            password=passphrase_bytes,
            backend=default_backend(),
        )

    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # 3. Connection setup
    print("Connecting to Snowflake...")
    conn = snowflake.connector.connect(
        user=secrets["user"],
        account=secrets["account"],
        private_key=pkb,
        warehouse=secrets.get("warehouse", "COMPUTE_WH"),
        database="SYNTHEA_PROD",
        schema="PUBLIC",
        role=secrets.get("role", "ACCOUNTADMIN"),
    )

    cursor = conn.cursor()

    try:
        # 4. Table count and exact row count from metadata (no table scan). LOAD_METRICS is bookkeeping.
        print("Querying table schema metadata...")
        cursor.execute("""
            SELECT
                COUNT(*) AS total_tables,
                COALESCE(SUM(ROW_COUNT), 0) AS total_system_rows
            FROM SYNTHEA_PROD.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'PUBLIC' AND TABLE_TYPE = 'BASE TABLE' AND TABLE_NAME <> 'LOAD_METRICS';
        """)
        table_count, total_system_rows = cursor.fetchone()

        # 5. Running totals. Patient-years: living patients count up to today, so LOAD_METRICS stores the
        # parts (living count, sum of living birth dates as day numbers, finished lifespans in days).
        print("Querying running totals from LOAD_METRICS...")
        cursor.execute(METRICS_CTE + """
            SELECT
                SUM(IFF(TABLE_NAME = 'PATIENTS', RECORD_COUNT, 0)),
                SUM(IFF(TABLE_NAME = 'CLAIMS', RECORD_COUNT, 0)),
                SUM(IFF(TABLE_NAME IN ('ENCOUNTERS', 'PROCEDURES'), RECORD_COUNT, 0)),
                SUM(IFF(TABLE_NAME = 'CLAIMS', AMOUNT_SUM, 0)),
                SUM(IFF(TABLE_NAME = 'EXPLANATION_OF_BENEFITS', AMOUNT_SUM, 0)),
                ( SUM(IFF(TABLE_NAME = 'PATIENTS', LIVING_PATIENTS, 0)) * DATEDIFF('day', '1970-01-01'::DATE, CURRENT_DATE)
                  - SUM(IFF(TABLE_NAME = 'PATIENTS', LIVING_BIRTH_DAYS_SUM, 0))
                  + SUM(IFF(TABLE_NAME = 'PATIENTS', DECEASED_LIFESPAN_DAYS_SUM, 0)) ) / 365.25
            FROM m;
        """)
        patients, claims, enc_proc, charges, payments, patient_years = cursor.fetchone()

        # 6. Daily trend: patients added per day (UTC).
        print("Querying patients-added daily trend...")
        cursor.execute(METRICS_CTE + """
            SELECT TO_VARCHAR(CONVERT_TIMEZONE('UTC', LOADED_AT)::DATE, 'YYYY-MM-DD') AS added_date,
                   SUM(RECORD_COUNT) AS patient_count
            FROM m WHERE TABLE_NAME = 'PATIENTS'
            GROUP BY 1 ORDER BY 1;
        """)
        trend_rows = cursor.fetchall()

        # 6b. Hourly trend (UTC, last 14 days): patients added and rows added across every table.
        print("Querying hourly patients/rows trend...")
        cursor.execute(METRICS_CTE + """
            SELECT TO_VARCHAR(DATE_TRUNC('hour', CONVERT_TIMEZONE('UTC', LOADED_AT)::TIMESTAMP_NTZ),
                              'YYYY-MM-DD HH24:MI:SS') AS h,
                   SUM(IFF(TABLE_NAME = 'PATIENTS', RECORD_COUNT, 0)),
                   SUM(ROW_COUNT)
            FROM m WHERE LOADED_AT >= DATEADD(day, -14, CURRENT_TIMESTAMP())
            GROUP BY 1 ORDER BY 1;
        """)
        hourly = [{"hour": h, "patients": int(p or 0), "rows": int(r or 0)} for h, p, r in cursor.fetchall()]

        # 6c. Batch cadence over the last 24 hours (real pipeline runs only, not the hourly backfill rows).
        print("Querying batch cadence...")
        cursor.execute(METRICS_CTE + """
            SELECT COUNT(DISTINCT RUN_TAG),
                   SUM(IFF(TABLE_NAME = 'PATIENTS', RECORD_COUNT, 0)),
                   DATEDIFF('second', MIN(LOADED_AT), MAX(LOADED_AT)),
                   TO_VARCHAR(CONVERT_TIMEZONE('UTC', MAX(LOADED_AT)), 'YYYY-MM-DD HH24:MI:SS')
            FROM m
            WHERE RUN_TAG NOT LIKE 'backfill%' AND LOADED_AT >= DATEADD(hour, -24, CURRENT_TIMESTAMP());
        """)
        runs, run_patients, span_s, last_load = cursor.fetchone()
        cadence = {
            "batches_24h": int(runs or 0),
            "patients_per_batch": round(run_patients / runs) if runs else None,
            "minutes_between_batches": round(span_s / 60 / (runs - 1), 1) if runs and runs > 1 else None,
            "last_batch_utc": last_load,
        }

        # 7. Package Payload
        payload = {
            "metrics": {
                "total_tables": table_count,
                "unique_patients": int(patients or 0),
                "unique_claims": int(claims or 0),
                "encounters_plus_procedures": int(enc_proc or 0),
                "total_rows": total_system_rows,
                "total_charges": float(charges or 0),
                "total_payments": float(payments or 0),
                "patient_years": float(patient_years or 0),
            },
            "cadence": cadence,
            "trend": [{"date": row[0], "count": int(row[1])} for row in trend_rows],
            "trend_hourly": hourly,
        }

        # 8. Write to JSON atomically
        with open("snowflake_cache.tmp", "w") as f:
            json.dump(payload, f, default=str)

        os.replace("snowflake_cache.tmp", "snowflake_cache.json")
        print("Successfully generated clean snowflake_cache.json!")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    fetch_and_cache_metrics()
