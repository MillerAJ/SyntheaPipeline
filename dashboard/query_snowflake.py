import json
import os
import re
import snowflake.connector
import toml
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization


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
        # 4. Fetch Total Table Count and Total Row Count directly from metadata
        print("Querying table schema metadata...")
        cursor.execute("""
            SELECT 
                COUNT(*) AS total_tables,
                COALESCE(SUM(ROW_COUNT), 0) AS total_system_rows
            FROM SYNTHEA_PROD.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'PUBLIC' AND TABLE_TYPE = 'BASE TABLE';
        """)
        meta_row = cursor.fetchone()
        table_count = meta_row[0]
        total_system_rows = meta_row[1]

        # 5. Direct Aggregations for Specific Known Tables
        print("Querying direct metrics for core entities...")
        cursor.execute("""
            SELECT
                (SELECT COUNT(DISTINCT PATIENT_ID) FROM SYNTHEA_PROD.PUBLIC.PATIENTS) AS unique_patients,
                (SELECT COUNT(DISTINCT CLAIM_ID) FROM SYNTHEA_PROD.PUBLIC.CLAIMS) AS unique_claims,
                (SELECT COUNT(DISTINCT ENCOUNTER_ID) FROM SYNTHEA_PROD.PUBLIC.ENCOUNTERS) AS total_encounters,
                (SELECT COUNT(DISTINCT PROCEDURE_ID) FROM SYNTHEA_PROD.PUBLIC.PROCEDURES) AS total_procedures,
                (SELECT COUNT(DISTINCT CODE) FROM SYNTHEA_PROD.PUBLIC.MEDICATIONS) AS unique_medications,
                (SELECT COUNT(DISTINCT PATIENT_ID) FROM SYNTHEA_PROD.PUBLIC.PATIENTS WHERE INSERTED_AT IS NULL) AS patients_undated;
        """)
        metrics_row = cursor.fetchone()

        # 6. Daily Trend: patients added to the database per day (UTC).
        # INSERTED_AT is the epoch time the patient's bundle was loaded into the pipeline.
        # Older patients without a load timestamp are counted separately (patients_undated).
        print("Querying patients-added daily trend...")
        cursor.execute("""
            SELECT
                TO_VARCHAR(TO_TIMESTAMP_NTZ(INSERTED_AT)::DATE, 'YYYY-MM-DD') AS added_date,
                COUNT(DISTINCT PATIENT_ID) AS patient_count
            FROM SYNTHEA_PROD.PUBLIC.PATIENTS
            WHERE INSERTED_AT IS NOT NULL
            GROUP BY 1
            ORDER BY 1 ASC;
        """)
        trend_rows = cursor.fetchall()

        # 6b. Hourly trend (UTC, last 14 days): patients added and rows added across every
        # PUBLIC table that carries INSERTED_AT. Legacy rows (NULL INSERTED_AT) are excluded.
        print("Querying hourly patients/rows trend...")
        cursor.execute("""
            SELECT TABLE_NAME
            FROM SYNTHEA_PROD.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'PUBLIC' AND COLUMN_NAME = 'INSERTED_AT'
            ORDER BY TABLE_NAME;
        """)
        ins_tables = [r[0] for r in cursor.fetchall() if re.fullmatch(r"[A-Z0-9_]+", r[0])]
        window = "INSERTED_AT >= DATE_PART(epoch_second, DATEADD(day, -14, CURRENT_TIMESTAMP()))"
        hour_expr = "TO_VARCHAR(DATE_TRUNC('hour', TO_TIMESTAMP_NTZ(INSERTED_AT)), 'YYYY-MM-DD HH24:MI:SS')"
        union_sql = " UNION ALL ".join(
            f"SELECT {hour_expr} AS h, COUNT(*) AS n FROM SYNTHEA_PROD.PUBLIC.{t} WHERE {window} GROUP BY 1"
            for t in ins_tables
        )
        cursor.execute(f"SELECT h, SUM(n) FROM ({union_sql}) GROUP BY 1 ORDER BY 1;")
        rows_by_hour = {r[0]: int(r[1]) for r in cursor.fetchall()}
        cursor.execute(f"""
            SELECT {hour_expr} AS h, COUNT(DISTINCT PATIENT_ID)
            FROM SYNTHEA_PROD.PUBLIC.PATIENTS
            WHERE {window}
            GROUP BY 1 ORDER BY 1;
        """)
        patients_by_hour = {r[0]: int(r[1]) for r in cursor.fetchall()}
        hourly = [
            {"hour": h, "patients": patients_by_hour.get(h, 0), "rows": rows_by_hour.get(h, 0)}
            for h in sorted(set(rows_by_hour) | set(patients_by_hour))
        ]

        # 7. Package Payload
        payload = {
            "metrics": {
                "total_tables": table_count,
                "unique_patients": metrics_row[0],
                "unique_claims": metrics_row[1],
                "encounters_plus_procedures": metrics_row[2]+metrics_row[3],
                "unique_medications": metrics_row[4],
                "total_rows": total_system_rows,
                "patients_undated": metrics_row[5],
            },
            "trend": [{"date": row[0], "count": row[1]} for row in trend_rows],
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
