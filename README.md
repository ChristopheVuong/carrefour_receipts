# carrefour_receipts

Extract, model and analyze personal Carrefour receipts with a modern data stack:
**dlt → DuckDB → dbt**, plus a Streamlit analytics dashboard.

<p align="center">
    <a href=""><img src="https://img.shields.io/badge/python-3.13-aff.svg"></a>
    <a href=""><img src="https://img.shields.io/badge/os-linux%2C%20win%2C%20mac-pink.svg"></a>
</p>

## What it does

Receipts (and loyalty/fidélité operations) are scraped from the Carrefour portal as
JSON/CSV, loaded into DuckDB with **dlt**, transformed into a tested star schema with
**dbt**, and surfaced as KPIs in a **Streamlit** dashboard. Highlights:

- One-to-one fidélité matching (Hungarian algorithm over rapidfuzz similarity).
- Keyword-based product categorization (food / hygiene_beauty / household / other).
- Analytics marts: monthly spend & rolling/YoY trends, category shares, price evolution,
  quantities.

## Quickstart

Tooling is managed with [uv](https://docs.astral.sh/uv/). Configuration lives in `.env`
(copy from `.env.example`; it is git-ignored).

```bash
uv sync --extra elt --extra analysis     # install
cp .env.example .env                      # configure
make build                                # dlt load (fixtures -> DuckDB) + dbt build + tests
make test                                 # offline tests with coverage
make dashboard                            # Streamlit dashboard over the marts
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
