# Synthea Pipeline

An end-to-end healthcare data pipeline: it generates synthetic patient records with
[Synthea](https://github.com/synthetichealth/synthea), stages them in PostgreSQL, flattens them with dbt,
and loads them into Snowflake through Snowpipe, in small batches, around the clock.

Live dashboard: [alexanderjmiller.com](https://alexanderjmiller.com)

```
Synthea (FHIR JSON) ──► PostgreSQL staging ──► dbt (32 flat tables) ──► Snowpipe ──► Snowflake
     DAG 01               raw.fhir_bundles        DAG 02                  DAG 03      SYNTHEA_PROD.PUBLIC
                                                                                            │
                                     DAG 04: clears staging after a confirmed load          ▼
                                                                          Streamlit dashboard, Metabase
```

## How often data lands in Snowflake

| | |
|---|---|
| **Schedule** | `dag_00_master` is scheduled every **5 minutes** (`*/5 * * * *`), one run at a time (`max_active_runs=1`), no catch-up. |
| **Run time** | A full run takes about **3 to 6 minutes** (generate ~1 min, dbt ~3 min, Snowpipe load ~1 min, cleanup seconds). |
| **In practice** | Runs go **back to back**: a new batch starts within moments of the last one finishing, about **10 to 12 batches an hour**. |
| **Batch size** | Set by `SYNTHEA_PATIENTS` in `.env`. The live deployment produces about **110 patients per batch**, roughly **400,000 rows** across 32 tables. |
| **Throughput** | About **1,300 patients an hour** (~30,000 a day) while the pipeline is running. |

Each batch is pushed to Snowflake with **Snowpipe**, not a warehouse: Parquet files go to an internal stage
and Snowpipe loads them serverlessly. Snowpipe bills per GB loaded, so running small batches often costs the
same as running large batches rarely. The cadence is chosen for freshness, not cost.

The pipeline can be paused at any time from Airflow (pause `dag_00_master` between runs, not during one).
The dashboard's **Patients Added Per Hour** chart shows when it was running.

## The DAGs

| DAG | What it does |
|---|---|
| `dag_00_master` | Runs 01 → 02 → 03 → 04 in order, every 5 minutes. |
| `dag_01_generate_and_load` | Runs Synthea for `SYNTHEA_PATIENTS` patients and loads each FHIR bundle into `raw.fhir_bundles`. |
| `dag_02_dbt_transform` | dbt builds 20 FHIR resource tables plus 12 child tables (claim items, observation components, ...) in the `flat` schema, then runs the tests in `_models.yml`. |
| `dag_03_snowflake_push` | Writes each flat table to Parquet, stages it, and triggers that table's Snowpipe. Waits until Snowflake reports every file `LOADED` with the exact row count. |
| `dag_04_postgres_cleanup` | Truncates staging, but only if the latest DAG 03 run succeeded (fails closed). |

## Reliability

- **Fails loudly.** Any failed table raises, so the run goes red and staging is kept for the next run.
  Every task has a 30-minute timeout, so one hung task can't freeze the schedule.
- **No double loads.** When a push fails partway, the next run pushes the kept staging rows again. DAG 03
  keeps a per-table high-water mark (`pipeline_control.push_watermark`, the highest `RAW_ID` Snowflake
  confirmed), so the retry skips rows that already landed. `RAW_ID` is the staging table's serial id, so it
  only grows. If it ever goes backwards (staging recreated), DAG 03 stops with an error instead of
  silently skipping data.
- **No hidden defaults.** Every setting comes from `.env` (see `.env.example`); a missing value stops the
  task that needs it, with an error naming it.

## Dashboard totals without full scans

For every table Snowflake confirms, DAG 03 records that batch's row count, record count, money totals and
patient-age inputs, and loads them into a small `LOAD_METRICS` table through its own Snowpipe. The dashboard
(`dashboard/query_snowflake.py`) sums that table, a few thousand rows, instead of scanning about a billion.
History from before the pipeline started recording was backfilled into the same table by the hour.

## Running it

1. Copy `.env.example` to `.env` and fill in every value (staging Postgres, Synthea folder and batch size,
   dbt paths, Snowflake account and key-pair settings).
2. `docker compose up -d` starts Airflow 2.9.3 (webserver, scheduler, metadata DB) and Marquez for lineage.
3. Unpause the DAGs in Airflow. `dag_00_master` takes it from there.

Snowflake objects (one table and one `<TABLE>_PIPE` per flat table, plus `LOAD_METRICS` and
`LOAD_METRICS_PIPE`, all reading from `SNOWPIPE_STAGE`) are created ahead of time; the pipeline itself never
runs DDL in Snowflake.

## Layout

```
dags/            Airflow DAGs (00-04) and pipeline_env.py (settings loader)
dbt_synthea/     dbt project: base model + 32 flat models, tests, macros
dashboard/       Streamlit app (app.py) and the Snowflake metrics query (query_snowflake.py)
docker-compose.yml, marquez.yml, .env.example
```
