# Financial assistant (natural-language text-to-SQL)

A chat assistant over the DuckDB marts: ask a question in plain language, it generates
**read-only** SQL, runs it, and shows the SQL, a result table and a Plotly chart when
relevant. It answers both from the pre-aggregated **marts** and via **ad-hoc aggregation
on the fact tables** (e.g. daily spend, per-product, per-VAT).

Surface: a Streamlit page (`Assistant`) inside the dashboard.

```bash
make build          # marts must exist
make assistant      # dashboard + assistant page → http://localhost:8501
```

## Architecture

```
question ─▶ Vanna 2.0 Agent (LLM, OpenAI-compatible)
              │   system prompt = schema card (dbt manifest + curated Q→SQL examples)
              ├─ run_sql  → ReadOnlyDuckDBRunner ─ sqlglot guard ─ duckdb(read_only) → DataFrame
              └─ visualize_data → Plotly figure
            ▼
   Streamlit: narration + SQL + table + chart
```

- **Vanna 2.0** ([vanna-ai/vanna](https://github.com/vanna-ai/vanna), MIT) — agent with two
  tools: `run_sql` and `visualize_data` (Plotly). Code in
  [src/carrefour_receipts_api/assistant/](../src/carrefour_receipts_api/assistant/).
- **Grounding** ([grounding.py](../src/carrefour_receipts_api/assistant/grounding.py)) — Vanna 2.0
  has no `vn.train()`; the schema is injected as the **system prompt** (`schema_card()`): table
  grains + column types (live DuckDB introspection) + descriptions (dbt `manifest.json`) + curated
  question→SQL examples. The small schema fits entirely in the prompt — no vector store needed.
- **Read-only safety** ([sql_guard.py](../src/carrefour_receipts_api/assistant/sql_guard.py) +
  [read_only_runner.py](../src/carrefour_receipts_api/assistant/read_only_runner.py)) — every
  generated query is parsed with **sqlglot** and must be a single `SELECT`/CTE over the
  **analytical layer** (`main.{fct_,dim_,int_,mart_}`). Writes/DDL, multi-statements, file-reading
  functions (`read_csv`/`read_parquet`/…), and the PII tables (`raw.*`, `stg_*` which holds the
  loyalty card number) are rejected — and the DuckDB connection itself is opened `read_only`.

## LLM provider — OpenAI or Ollama (OpenAI-compatible)

Configured in `.env` (see [.env.example](../.env.example)). The OpenAI SDK honours `base_url`,
so any OpenAI-compatible endpoint works:

| Provider | `ASSISTANT_LLM_BASE_URL` | `ASSISTANT_LLM_API_KEY` | `ASSISTANT_MODEL` |
| --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | your key | `gpt-4o-mini` |
| Ollama (local, free) | `http://localhost:11434/v1` | any dummy value | e.g. `qwen2.5-coder` |

> No Claude/Anthropic provider. (A Claude *Max* subscription can't be used by a standalone app —
> it needs an API key — so it is out of scope here.)

## Usage examples

- « Combien ai-je dépensé par catégorie cette année ? » (marts)
- « Magasin vs Drive : combien sur chaque canal ? » (`channel` dimension)
- « Combien la cagnotte fidélité m'a fait gagner cette année ? » (`mart_loyalty_savings`)
- « Mes courses jour par jour ce mois-ci » (**ad-hoc** on `int_purchases` facts)
- « Top 10 des produits les plus achetés » · « Évolution du prix moyen du lait »

## Tech-survey rationale (why this stack)

- **dbt Semantic Layer / dbt-mcp querying** — requires dbt Cloud (paid); not available for local
  dbt-Core + DuckDB. We reuse the free part: the local dbt **metadata** as grounding context.
- **Airbyte** — ingestion tool, irrelevant (we use dlt). **LangGraph** — orchestration overkill
  for a ~15-table schema. Both excluded.
- **Vanna 2.0** chosen for batteries-included agent + Plotly viz; **sqlglot** for the read-only
  guardrail.

## Tests

[tests/unit/test_assistant_guard.py](../tests/unit/test_assistant_guard.py) (allowlist / read-only
rejection) and [test_assistant_grounding.py](../tests/unit/test_assistant_grounding.py)
(schema card) — pure, no LLM/network; skipped when the `assistant` extra isn't installed.
