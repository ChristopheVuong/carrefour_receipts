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
LOYALTY_SOURCE_CSV: str = _get("LOYALTY_SOURCE_CSV", "tests/fixtures/loyalty/loyalty.csv")

# Minimum similarity (0..1) for a loyalty item label to be accepted as a match
# against a receipt product label in the fidélité one-to-one join (dbt Python
# model int_loyalty_matched). Env-driven so the dbt run can read it.
FIDELITY_MATCH_THRESHOLD: float = float(_get("FIDELITY_MATCH_THRESHOLD", "0.85"))
