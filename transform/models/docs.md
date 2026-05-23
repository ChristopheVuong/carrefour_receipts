---
noteId: "84af4fb055fb11f19ea30b15726f8543"
tags: []

---

{% docs __overview__ %}

# Carrefour Receipts — Data Mart

This is the **dbt documentation** for the Carrefour receipts data mart. It is generated
directly from the dbt project (`dbt docs generate`) and is self-contained: model lineage,
column descriptions and tests all come from the project itself, independent of the
repository README.

## Pipeline

```
Carrefour API ──(curl/cookies)──▶ JSON / CSV in data/
        │
        ▼  dlt  (carrefour_receipts_api.elt.load)
   raw schema in DuckDB
        │
        ▼  dbt
   staging  ──▶  intermediate  ──▶  marts  ──▶  marts/analytics
```

## Layers

- **staging** (views) — one model per raw entity, renamed/typed: `stg_receipts`,
  `stg_receipt_lines`, `stg_loyalty`, `stg_payments`.
- **intermediate** (tables) — enrichment that needs Python:
  - `int_loyalty_matched` — the fidélité one-to-one join.
  - `int_product_categorized` — keyword product categorization.
- **marts** (tables) — the star schema: facts `fct_receipts`, `fct_receipt_lines`,
  `fct_loyalty_lines` and dimension `dim_date`.
- **marts/analytics** (tables) — presentation KPIs: `mart_monthly_spend`,
  `mart_category_insights`, `mart_product_prices`, `mart_quantities`, built over the
  gap-free `dim_month_spine`.

## Conventions

- `stg_*` clean & rename only; `int_*` enrich; `fct_*`/`dim_*` are the consumable star
  schema; `mart_*` are aggregate/presentation models.
- Thresholds for the Python models are environment-driven (`config.py`), not dbt vars —
  dbt vars are not visible inside dbt-duckdb Python models.

{% enddocs %}


{% docs fidelity_matching %}
Each loyalty line is matched to **at most one** receipt product line purchased the same
day, and each receipt line to at most one loyalty line — an optimal one-to-one assignment
(Hungarian algorithm, `scipy.optimize.linear_sum_assignment`) over a rapidfuzz
string-similarity matrix. This replaces the previous greedy SQL, which let one receipt
label be claimed by several loyalty lines and dropped quantities via `select distinct`.
The logic lives in `carrefour_receipts_api.matching` and is unit-tested; the threshold is
`config.FIDELITY_MATCH_THRESHOLD`.
{% enddocs %}


{% docs product_categorization %}
Product labels are classified into a coarse `category` (food / hygiene_beauty / household
/ other) and a finer `subcategory` by fuzzy-matching (rapidfuzz `partial_ratio`) against
the curated `seed_product_categories` keyword table. A label scoring below
`config.CATEGORY_MATCH_THRESHOLD` gets a NULL category and falls back to the VAT-based
heuristic (`vat_category`) downstream. Logic lives in
`carrefour_receipts_api.categorization` (no fastembed required, so it runs in CI).
{% enddocs %}


{% docs loyalty_line_id %}
Stable, unique grain of a loyalty line. A loyalty line has no natural key
(`operationId` repeats across an operation's items; `_dlt_id` changes each load), so this
is a deterministic key — `md5(content signature | occurrence index)` — computed in
`stg_loyalty` from the unnested `loyalty__history` rows. Same content always yields the same
key, so it is stable across rebuilds. The `loyalty` source itself is merged on the month
`_id`, so DuckDB accumulates history across loads even though the live API only returns a
rolling ~1-year window.
{% enddocs %}


{% docs month_spine %}
A gap-free monthly series from the first to the last receipt month. The observed-date
dimension (`dim_date`) is sparse — months with no shopping are absent — which would make
rolling 3/6/12-month and year-over-year (lag-12) windows span the wrong period. Every
time-series analytics mart left-joins onto this spine so empty months count as zero and
the windows are correct.
{% enddocs %}
