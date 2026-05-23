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

from carrefour_receipts_api.secrets_store import read_secrets

# Walk up from the current working directory to find a .env (no error if absent).
load_dotenv(find_dotenv(usecwd=True))


def _get(name: str, default: str) -> str:
    return os.getenv(name, default)


# --- Filesystem / extraction ------------------------------------------------
DATA_DIRECTORY: str = _get("DATA_DIRECTORY", "data")
COOKIES_FILE: str = _get("COOKIES_FILE", f"{DATA_DIRECTORY}/cookies.txt")
SECRETS_FILE: str = _get("SECRETS_FILE", f"{DATA_DIRECTORY}/secrets.yml")

# --- Loyalty / fidélité identifiers (PII — keep out of git, never commit) ----
# Carrefour card numbers used as query params on the receipt/loyalty endpoints.
# Resolution: the environment variable wins (override), else the value captured by
# the auth service into SECRETS_FILE (data/secrets.yml), else empty. The auth
# service scrapes these from the account page or takes them from a manual form.
_secrets = read_secrets(SECRETS_FILE)
LOYALTY_CARD_NUMBER: str = os.getenv("LOYALTY_CARD_NUMBER") or _secrets.get("loyaltyCardNumber", "")
PASS_CARD_NUMBER: str = os.getenv("PASS_CARD_NUMBER") or _secrets.get("passCardNumber", "")

# --- Carrefour auth portal (used by the FastAPI auth service) ---------------
# Where to send the user to authenticate, and the account area we expect after a
# successful login (used to detect completion and harvest the session cookies).
CARREFOUR_LOGIN_URL: str = _get("CARREFOUR_LOGIN_URL", "https://www.carrefour.fr/login")
CARREFOUR_ACCOUNT_URL: str = _get("CARREFOUR_ACCOUNT_URL", "https://www.carrefour.fr/mon-compte")
# Authenticated JSON endpoint listing the account's loyalty / Pass cards (each with its
# loyaltyCardNumber + loyaltyCardType); queried after login to capture them.
CARREFOUR_CARDS_URL: str = _get(
    "CARREFOUR_CARDS_URL", "https://www.carrefour.fr/api/user/secured/loyalty/my-cards"
)

# Persistent browser profile for the Playwright login flow. Reusing a real profile
# (history, prior Turnstile passes) makes the browser look like a returning user, so
# Cloudflare Turnstile is far less likely to challenge. Lives under data/ (git-ignored).
BROWSER_PROFILE_DIR: str = _get("BROWSER_PROFILE_DIR", f"{DATA_DIRECTORY}/browser_profile")

# Which real browser Playwright should drive (real-browser fingerprints clear Turnstile
# far better than bundled Chromium). Empty = auto: try Chrome, then Edge, then Chromium.
# Set to a Playwright channel ("chrome", "msedge", ...) to force one.
BROWSER_CHANNEL: str = _get("BROWSER_CHANNEL", "")

# TLS fingerprint the extractor's HTTP client (curl_cffi) impersonates. Cloudflare binds
# the cf_clearance cookie to the JA3 of the browser that solved the challenge, so plain
# curl/requests/httpx (OpenSSL) get a 403; curl_cffi reproduces a real browser handshake.
# Must match the browser family used for the auth-service login (default Edge).
CARREFOUR_TLS_IMPERSONATE: str = _get("CARREFOUR_TLS_IMPERSONATE", "edge101")

# --- Modern data stack (dlt -> DuckDB -> dbt) -------------------------------
DUCKDB_PATH: str = _get("DUCKDB_PATH", "carrefour.duckdb")
DUCKDB_DATASET: str = _get("DUCKDB_DATASET", "raw")
RECEIPTS_SOURCE_DIR: str = _get("RECEIPTS_SOURCE_DIR", "tests/fixtures/receipts")
LOYALTY_SOURCE_DIR: str = _get("LOYALTY_SOURCE_DIR", "tests/fixtures/loyalty")
ORDERS_SOURCE_DIR: str = _get("ORDERS_SOURCE_DIR", "tests/fixtures/orders")

# Minimum similarity (0..1) for a loyalty item label to be accepted as a match
# against a receipt product label in the fidélité one-to-one join (dbt Python
# model int_loyalty_matched). Env-driven so the dbt run can read it.
FIDELITY_MATCH_THRESHOLD: float = float(_get("FIDELITY_MATCH_THRESHOLD", "0.85"))

# --- Product categorization (dbt Python model int_product_categorized) ------
# Minimum similarity (0..1) for a seed keyword to classify a product label; below
# it the label falls back to the VAT-based category. Env-driven (dbt vars aren't
# visible to Python models).
CATEGORY_MATCH_THRESHOLD: float = float(_get("CATEGORY_MATCH_THRESHOLD", "0.80"))
# Opt-in to the fastembed (ONNX) semantic categorizer instead of rapidfuzz. Off by
# default so CI (which installs only elt + analysis, not the ml extra) stays fast
# and deterministic.
CATEGORY_USE_EMBEDDINGS: bool = _get("CATEGORY_USE_EMBEDDINGS", "false").lower() == "true"
