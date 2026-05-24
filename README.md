<h1 align="center">Carrefour receipts analyzer</h1>

<p align="center">
<strong>Personal grocery analytics.</strong><br>
dlt → DuckDB → dbt pipeline · Streamlit dashboard · natural-language SQL assistant.
</p>

<p align="center">
<a href="https://github.com/ChristopheVuong/carrefour_receipts/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ChristopheVuong/carrefour_receipts/actions/workflows/ci.yml/badge.svg"></a>
<a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
<img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-aff.svg">
<img alt="Linux, Win, Mac" src="https://img.shields.io/badge/os-linux%2C%20win%2C%20mac-pink.svg">
</p>

<br>

## What it does

End-to-end personal grocery analytics — from browser login to conversational insights.

**🔐 Browser authentication** — Playwright opens a real Chrome/Edge browser, solves Cloudflare Turnstile, and auto-captures the loyalty and Pass card numbers used to query the Carrefour API. Single-tenant today; card number is the natural key for a multi-user extension.

**📥 Extraction pipeline** — pulls in-store receipts, Drive orders and fidélité operations from the authenticated API, loads them into DuckDB via dlt, and transforms them into analytics-ready marts with dbt.

**📊 Dashboard + NL assistant** — a Streamlit dashboard (KPIs, spend trends, category breakdown, price evolution) paired with a conversational assistant: ask in French, get read-only SQL, a result table and a Plotly chart — powered by Vanna 2.0 + LLM provider (either Openai API or Ollama as of now).

## Prerequisites

| Tool | Version | Install |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.5 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` (Linux/Mac) · `winget install astral-sh.uv` (Windows) |
| Python | 3.13 | `uv python install 3.13` — managed automatically by uv, no system Python needed |
| GNU Make | any | pre-installed on Linux/Mac · `winget install GnuWin32.Make` on Windows |
| Chrome or Edge | latest | required by the Playwright auth service for live data extraction (not needed for the fixture-based quickstart) |

## Quickstart

The quickstart uses bundled test fixtures — no Carrefour account required.

```bash
uv sync --extra elt --extra analysis   # install dependencies
cp .env.example .env                   # configure paths and keys (.env is git-ignored)
make build                             # load fixtures into DuckDB + dbt build + tests
make dashboard                         # analytics dashboard  →  http://localhost:8501
make assistant                         # dashboard + NL assistant (requires ASSISTANT_LLM_API_KEY in .env)
```

### Live data extraction (Carrefour account required)

```bash
make auth-service   # opens a browser (Chrome/Edge via Playwright) to log in
make elt            # extract receipts + loyalty data, load into DuckDB
make build          # rebuild dbt models on real data
```

> The browser login uses Playwright with a persistent profile to pass Cloudflare Turnstile.
> Set `BROWSER_CHANNEL=chrome` (or `msedge`) in `.env` to force a specific browser.

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
| [docs/assistant.md](docs/assistant.md) | Natural-language SQL assistant (Vanna 2.0 + OpenAI, architecture + setup) |
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
