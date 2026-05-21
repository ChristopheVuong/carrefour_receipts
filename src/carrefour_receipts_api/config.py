"""Central configuration, loaded from environment variables (and a local .env).

Importing this module calls ``load_dotenv`` once, so any entry point that needs
configuration just imports the constants below. Keeping paths, connection
strings and the DuckDB location here (instead of hard-coded literals scattered
across modules) is the security/ops fix flagged in the audit: secrets and
environment-specific values live in ``.env`` (git-ignored), not in the code.

See ``.env.example`` for the full list of supported variables.
"""

from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv

# Walk up from the current working directory to find a .env (no error if absent).
load_dotenv(find_dotenv(usecwd=True))


def _get(name: str, default: str) -> str:
    return os.getenv(name, default)


# --- Filesystem / extraction ------------------------------------------------
DATA_DIRECTORY: str = _get("DATA_DIRECTORY", "data")
COOKIES_FILE: str = _get("COOKIES_FILE", f"{DATA_DIRECTORY}/cookies.txt")
SECRETS_FILE: str = _get("SECRETS_FILE", f"{DATA_DIRECTORY}/secrets.yml")

# --- Modern data stack (dlt -> DuckDB -> dbt) -------------------------------
DUCKDB_PATH: str = _get("DUCKDB_PATH", "carrefour.duckdb")
DUCKDB_DATASET: str = _get("DUCKDB_DATASET", "raw")
RECEIPTS_SOURCE_DIR: str = _get("RECEIPTS_SOURCE_DIR", "tests/fixtures/receipts")

# --- Legacy MongoDB path ----------------------------------------------------
MONGO_CONNECTION_STRING: str = _get("MONGO_CONNECTION_STRING", "mongodb://localhost:27017/")
MONGO_DB_NAME: str = _get("MONGO_DB_NAME", "carrefour")
