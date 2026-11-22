"""Required settings for the pipeline, read from the environment (the pipeline .env, loaded by docker compose).

There are deliberately NO default values: a missing setting stops the task before it touches anything, with an
error that names what is missing, instead of silently connecting somewhere else. Values are read when a task runs,
not when the scheduler parses the file, so a missing setting breaks the task, not the whole file.
"""
import os


def require_env(*names):
    """Return the value of each named environment variable (a single value for one name, else a list)."""
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required setting(s): " + ", ".join(missing)
            + ". Add them to the pipeline .env and recreate the containers (docker compose up -d)."
        )
    values = [os.environ[name] for name in names]
    return values[0] if len(values) == 1 else values


def staging_db_config():
    """Connection settings for the staging Postgres database (psycopg2 keyword names)."""
    host, port, dbname, user, password = require_env(
        "STAGING_DB_HOST", "STAGING_DB_PORT", "STAGING_DB_NAME", "STAGING_DB_USER", "STAGING_DB_PASSWORD"
    )
    return {"host": host, "port": port, "dbname": dbname, "user": user, "password": password}
