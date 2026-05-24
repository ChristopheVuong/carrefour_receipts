<h1 align="center">carrefour_receipts</h1>

<p align="center">
<strong>Vos courses, analysées.</strong><br>
Pipeline personnel dlt → DuckDB → dbt + dashboard Streamlit + assistant NL texte-vers-SQL.
</p>

<p align="center">
<a href="https://github.com/ChristopheVuong/carrefour_receipts/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ChristopheVuong/carrefour_receipts/actions/workflows/ci.yml/badge.svg"></a>
<a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
<img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-aff.svg">
<img alt="Linux, Win, Mac" src="https://img.shields.io/badge/os-linux%2C%20win%2C%20mac-pink.svg">
</p>

<br>

## What it does

Receipts (and loyalty/fidélité operations) are scraped from the Carrefour portal as
JSON/CSV, loaded into DuckDB with **dlt**, transformed into a tested star schema with
**dbt**, and surfaced as KPIs in a **Streamlit** dashboard + a natural-language
**SQL assistant** (Vanna 2.0 + OpenAI). Highlights:

- One-to-one fidélité matching (Hungarian algorithm over rapidfuzz similarity).
- Keyword-based product categorization (food / hygiene_beauty / household / other).
- Analytics marts: monthly spend & rolling/YoY trends, category shares, price evolution,
  quantities.
- Ask questions in plain French; the assistant generates read-only DuckDB SQL and renders
  results as tables and Plotly charts.

## Prérequis

| Outil | Version | Installation |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.5 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` (Linux/Mac) or `winget install astral-sh.uv` (Windows) |
| Python | 3.13 | `uv python install 3.13` (géré automatiquement par uv) |
| GNU Make | any | pré-installé sur Linux/Mac ; `winget install GnuWin32.Make` sur Windows |

## Quickstart

```bash
# 1 — dépendances
uv sync --extra elt --extra analysis

# 2 — configuration (.env est git-ignoré)
cp .env.example .env          # renseigner DATA_DIRECTORY, DUCKDB_PATH, etc.

# 3 — pipeline : extraction fixtures → DuckDB → dbt + tests
make build

# 4 — dashboard analytique  →  http://localhost:8501
make dashboard

# 5 — dashboard + assistant NL (nécessite ASSISTANT_LLM_API_KEY dans .env)
make assistant
```

## Documentation

This README is intentionally a short index. Detailed docs live in two **independent**
places:

### Codebase (`docs/`)

| Page | What it covers |
| --- | --- |
| [docs/usage.md](docs/usage.md) | **Start here** — full walkthrough: auth → extract → build → dashboard → refresh |
| [docs/architecture.md](docs/architecture.md) | End-to-end data flow and how the pieces fit |
| [docs/api-extraction.md](docs/api-extraction.md) | Scraping & authentication (cookies, Cloudflare), extractors |
| [docs/processing.md](docs/processing.md) | Matching, embeddings, categorization, loyalty merge key |
| [docs/dashboard.md](docs/dashboard.md) | Running the Streamlit dashboard (local + Docker) |
| [docs/deployment.md](docs/deployment.md) | Containerized batch ingestion (`make build` as a re-runnable job) |
| [docs/development.md](docs/development.md) | Setup, extras, Make targets, tests/CI, env vars |

### Data mart (dbt — generated, not hand-written)

The data mart is documented by dbt itself and is self-contained (model lineage, column
descriptions, tests). Generate and browse it with:

```bash
make docs-dbt        # dbt docs generate && dbt docs serve  (http://localhost:8080)
```

## License

MIT.
