---
noteId: "87e1f670555511f19bb6f1faf66f1118"
tags: []

---

# Development

## Setup

Tooling is [uv](https://docs.astral.sh/uv/). Python 3.13 (`.python-version`).

```bash
uv sync --extra elt --extra analysis     # = make install (dev + ELT + analysis)
cp .env.example .env
```

> If a stray `VIRTUAL_ENV` (e.g. a conda env) is active, prefix uv commands with
> `env -u VIRTUAL_ENV` so uv uses the project venv.

### Extras

| Extra | Brings | Needed for |
| --- | --- | --- |
| `elt` | dlt, duckdb, dbt-duckdb | the ELT + dbt pipeline |
| `analysis` | scikit-learn, scipy, rapidfuzz, matplotlib, seaborn | matching, categorization, plots |
| `ml` | fastembed (ONNX, no torch) | semantic embeddings (optional) |
| `scraping` | selenium, seleniumbase, playwright | browser-based extraction fallbacks |
| `dashboard` | streamlit, altair, duckdb | the analytics dashboard |

`structlog` ships in the core dependencies (structured logging).

## Make targets

| Target | Does |
| --- | --- |
| `make install` / `make install-ml` | sync deps (+ the `ml` extra) |
| `make lint` / `make format` / `make typecheck` | ruff check / ruff format / mypy on the modern stack |
| `make test` | offline tests with coverage (`-m "not integration"`) |
| `make elt` | dlt-load receipts + loyalty into DuckDB |
| `make dbt` | `dbt build` (models + tests) |
| `make build` | `elt` then `dbt` — the full pipeline |
| `make docs-dbt` | generate + serve the dbt documentation site |
| `make dashboard` | run the Streamlit dashboard |
| `make docker-build` / `make docker-run` | build / run the dashboard container |
| `make clean` | remove the DuckDB file and dbt artifacts |

## Loading your real data

The defaults point at committed fixtures. To load your own extracts, either edit `.env`
(`RECEIPTS_SOURCE_DIR`, `LOYALTY_SOURCE_CSV`) or pass flags:

```bash
uv run python -m carrefour_receipts_api.elt.load \
    --source data/20250613 \
    --loyalty data/20250601-carrefour_loyalty.csv \
    --dataset raw
```

## Tests

`pytest` markers (see `pyproject.toml`): `fast`, `slow` (embeddings; needs the `ml`
extra), `integration` (hits the live API; needs local cookies/secrets). CI runs
`-m "not integration"`. Coverage: `make test` adds `--cov=carrefour_receipts_api
--cov-report=term-missing`.

## CI

[.github/workflows/ci.yml](../.github/workflows/ci.yml) has two jobs, neither touching the
live API:

- **quality** — ruff lint + format check + mypy on the modern stack, then pytest with
  coverage.
- **data** — dlt-load the fixtures into DuckDB, then `dbt build` (the seed loads
  automatically; the `analysis` extra supplies rapidfuzz/scipy for the Python models).

## Environment variables

Loaded by [config.py](../src/carrefour_receipts_api/config.py) from `.env`. Full list and
defaults in [.env.example](../.env.example):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_DIRECTORY` | `data` | root for cookies/secrets/extracts |
| `COOKIES_FILE`, `SECRETS_FILE` | `data/cookies.txt`, `data/secrets.yml` | auth inputs |
| `DUCKDB_PATH` | `carrefour.duckdb` | DuckDB file (also read by the dbt profile) |
| `DUCKDB_DATASET` | `raw` | dlt target schema |
| `RECEIPTS_SOURCE_DIR`, `LOYALTY_SOURCE_CSV` | fixtures | ELT inputs |
| `FIDELITY_MATCH_THRESHOLD` | `0.85` | fidélité match cutoff |
| `CATEGORY_MATCH_THRESHOLD` | `0.80` | categorization cutoff |
| `CATEGORY_USE_EMBEDDINGS` | `false` | use fastembed for categorization |
| `LOG_LEVEL`, `LOG_JSON` | `INFO`, `false` | logging level / JSON output |

## Conventions

- Secrets and PII live in `.env` and `data/` — both git-ignored. Never commit them.
- dbt thresholds are env-driven (Python models can't read dbt `vars:`).
- Ruff/mypy are gated on the modern surface (config, embeddings, matching,
  categorization, logging, elt, dashboard, tests); legacy modules carry style debt.
