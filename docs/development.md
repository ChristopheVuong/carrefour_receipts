# Development

## Setup

Tooling is [uv](https://docs.astral.sh/uv/). Python 3.13 (`.python-version`).

```bash
uv sync --extra all                      # = make install (dev + the full local stack)
cp .env.example .env
uv run pre-commit install                # wire the git hooks (lint/type on commit, tests on push)
```

> Add `--extra scraping` when you need browser extraction / the auth service, and
> `--extra ml` for the optional semantic embeddings — both are kept out of `all` because
> they are heavy (selenium/playwright, ONNX). `make install-ml` = `all` + `ml`.

> If a stray `VIRTUAL_ENV` (e.g. a conda env) is active, prefix uv commands with
> `env -u VIRTUAL_ENV` so uv uses the project venv.

### Extras

| Extra | Brings | Needed for |
| --- | --- | --- |
| `all` | `elt` + `analysis` + `dashboard` + `api` | the full local stack (one flag; what `make install` uses) |
| `elt` | dlt, duckdb, dbt-duckdb | the ELT + dbt pipeline |
| `analysis` | scikit-learn, scipy, rapidfuzz, matplotlib, seaborn | matching, categorization, plots |
| `dashboard` | streamlit, altair, duckdb | the analytics dashboard |
| `api` | fastapi, uvicorn | the auth service (browser login → cookies) |
| `ml` | fastembed (ONNX, no torch) | semantic embeddings (optional, heavy — not in `all`) |
| `assistant` | vanna[openai,duckdb,chromadb], sqlglot | NL financial assistant page ([assistant.md](assistant.md)) — not in `all` |
| `scraping` | selenium, seleniumbase, playwright, patchright, curl_cffi | browser extraction + auth-service login (heavy — not in `all`) |

The granular extras still exist so the **Docker image** (`--extra dashboard` only) and **CI**
(`elt`/`analysis`, plus `dashboard`/`api` in the quality job) stay lean; `all` is a
convenience aggregate for local dev and does not change those.

`structlog` ships in the core dependencies (structured logging).

## Make targets

| Target | Does |
| --- | --- |
| `make install` / `make install-ml` | sync the full local stack (`all`) / also the `ml` extra |
| `make lint` / `make format` / `make format-check` / `make typecheck` | ruff check / ruff format (write) / ruff format (check only) / mypy on the modern stack |
| `make test` | offline tests with coverage (`-m "not integration"`) |
| `make elt` | dlt-load receipts + loyalty into DuckDB |
| `make dbt` | `dbt build` (models + tests) |
| `make build` | `elt` then `dbt` — the full pipeline |
| `make docs-dbt` | generate + serve the dbt documentation site |
| `make dashboard` | run the Streamlit dashboard |
| `make auth-service` | run the FastAPI auth service (browser login → cookies) |
| `make docker-build` / `make docker-run` | build / run the dashboard container |
| `make clean` | remove the DuckDB file, dbt artifacts and the dlt pipeline state (full reset) |

## Pre-commit hooks

[.pre-commit-config.yaml](../.pre-commit-config.yaml) mirrors the CI **quality** job using
the same tools and the same modern-stack scope. The hooks delegate to the Make targets, so
the scope is single-sourced (Makefile `STACK` ↔ CI ↔ pre-commit) and never drifts.

| Stage | Hooks |
| --- | --- |
| **commit** | `make lint` (ruff check), `make format-check` (ruff format --check), `make typecheck` (mypy), plus a large-file guard (PII) and merge-conflict check |
| **push** | `make test` (offline pytest, `-m "not integration"`) — keeps commits fast, blocks pushes that break tests |

```bash
uv run pre-commit install                 # one-time: wire commit + push hooks
uv run pre-commit run --all-files         # run the commit-stage hooks on demand
uv run pre-commit run --all-files --hook-stage pre-push   # also run the test hook
```

The push hook needs the `elt`/`analysis` extras installed (`make install`). To bypass in a
pinch: `git commit --no-verify` / `git push --no-verify`.

## Loading your real data

The defaults point at committed fixtures. To load your own extracts, either edit `.env`
(`RECEIPTS_SOURCE_DIR`, `LOYALTY_SOURCE_DIR`) or pass flags (both take a directory of JSON):

```bash
uv run python -m carrefour_receipts_api.elt.load \
    --source data \
    --loyalty data \
    --orders data \
    --dataset raw
```

`--pipelines-dir <path>` points dlt's pipeline state at a chosen directory (default: dlt's own
location). Used by the containerized batch to keep state on a persistent volume — see
[deployment.md](deployment.md).

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
| `LOYALTY_CARD_NUMBER`, `PASS_CARD_NUMBER` | _(empty)_ | fidélité card numbers (PII) — receipt/loyalty endpoint params. **Resolved env-var-first, then `SECRETS_FILE`** (the auth service scrapes/saves them there). |
| `CARREFOUR_CARDS_URL` | `…/loyalty/my-cards` | authenticated JSON endpoint the auth service reads for the card numbers |
| `CARREFOUR_TLS_IMPERSONATE` | `edge101` | curl_cffi browser TLS fingerprint (past Cloudflare) |
| `DUCKDB_PATH` | `carrefour.duckdb` | DuckDB file (also read by the dbt profile) |
| `DUCKDB_DATASET` | `raw` | dlt target schema |
| `RECEIPTS_SOURCE_DIR`, `LOYALTY_SOURCE_DIR`, `ORDERS_SOURCE_DIR` | fixtures | ELT inputs (dirs of JSON) |
| `CATEGORY_MATCH_THRESHOLD` | `0.80` | categorization cutoff |
| `CATEGORY_USE_EMBEDDINGS` | `false` | use fastembed for categorization |
| `LOG_LEVEL`, `LOG_JSON` | `INFO`, `false` | logging level / JSON output |

## Conventions

- Secrets and PII live in `.env` and `data/` — both git-ignored. Never commit them.
- dbt thresholds are env-driven (Python models can't read dbt `vars:`).
- Ruff/mypy are gated on the modern surface (config, embeddings, matching,
  categorization, logging, elt, dashboard, tests); legacy modules carry style debt.
