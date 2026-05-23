# Processing & matching

The Python processing layer holds the analytical logic that doesn't belong in SQL —
fuzzy matching helpers, embeddings, categorization. The categorization primitive is
imported by the dbt **Python model**, so it is kept free of heavy/plotting dependencies.

`matching.py` provides the shared rapidfuzz helpers (`preprocess` — lowercase + strip
diacritics; `fuzzy_match`) used by the categorization model. (There is no longer a
loyalty↔receipt fuzzy join: the `/loyalty/transactions` API exposes loyalty only at the
operation level, with no item labels to match — see the loyalty section below.)

## Product categorization — [categorization.py](../src/carrefour_receipts_api/categorization.py)

Classifies a product label into a coarse `category` (food / hygiene_beauty / household /
other) and a finer `subcategory`.

- `categorize_labels(labels, seed, threshold, scorer=fuzz.partial_ratio)` — fuzzy-matches
  each distinct label against the curated keyword seed
  ([transform/seeds/seed_product_categories.csv](../transform/seeds/seed_product_categories.csv)),
  keeping the best `(score, priority)` above `threshold`. Deterministic, rapidfuzz-only.
- `categorize_labels_semantic(...)` — optional embeddings variant; returns `None` if the
  `ml` extra is absent, so it never breaks a build.

Used by the dbt model `int_product_categorized`. Threshold:
`config.CATEGORY_MATCH_THRESHOLD` (default 0.80). Below the threshold a label falls back
to the VAT-based `vat_category` in `fct_receipt_lines`. Toggle the embeddings path with
`CATEGORY_USE_EMBEDDINGS=true` (local only).

## Embeddings — [embeddings.py](../src/carrefour_receipts_api/embeddings.py)

`load_encoder()` returns an `Encoder` wrapping **fastembed** (ONNX Runtime — no torch),
exposing a `.encode()` compatible with the old sentence-transformers call sites. ONNX
means it installs on macOS x86_64/Intel, where recent torch has no wheels. Install with
the `ml` extra. On Intel Macs, `onnxruntime` is pinned `<1.24` (see `pyproject.toml`
`[tool.uv]`).

## ELT — Loyalty merge & grain

The loyalty extract is one JSON document **per month** (`_id` = `YYYYMM`) carrying a
`history` array. The `/loyalty/transactions` endpoint returns **operation-level** entries
(`operationId`, `date`, `store`, `earned`, `burned`, `canceled`) — one per shopping trip's
cagnotte movement, **no per-item breakdown**. dlt unnests `history` into the child table
`raw.loyalty__history`, and the `loyalty` resource `merge`s on the month `_id`
([elt/load.py](../src/carrefour_receipts_api/elt/load.py)). So reloading a month replaces its
operations while older months (absent from a fresh ~1-year extract) are kept — DuckDB
**accumulates** history across loads, necessary because the API only returns a rolling
~1-year window (see [api-extraction.md](api-extraction.md)).

`stg_loyalty` keys on the natural `loyalty_operation_id`. `earned`/`burned` are float-coerced
in the load so dlt keeps a single DOUBLE column (`burned` is int on some rows). Monthly
fidélité savings (cagnotte earned, excluding canceled operations) roll up in
`mart_loyalty_savings`.

## ELT — Drive orders flatten

Drive order JSON nests each line's price under **dynamic dict keys**
(`attributes.offers[ean][offerId].attributes.price`), which dlt can't unnest into clean tables.
So `_flatten_order` ([elt/load.py](../src/carrefour_receipts_api/elt/load.py)) reshapes each order
in Python into `{header, payments[], lines[]}` (pulling out `unit_price`, `line_total`,
`immediate_discount`), and the `orders` resource `merge`s on `order_number`; dlt then unnests
`lines` → `raw.orders__lines` and `payments` → `raw.orders__payments`. Orders carry **no per-line
VAT**, so `stg_order_lines.vat_percentage` is null and the VAT category fallback is `other` — the
real category comes from the keyword classification (`int_product_categorized`, which now sees
both receipt and order labels).

## Marts — store + Drive unified by `channel`

The star schema keeps **separate facts** (`fct_receipts`/`fct_receipt_lines` and
`fct_orders`/`fct_order_lines`), then unions them line- and order-grain into `int_purchase_lines`
/ `int_purchases` tagged with a `channel` (`store` | `drive`). The four analytics marts read those
unions, so every time series is **per (month, channel)** — a BI layer (the dashboard) filters to a
channel or sums across them for an all-channel total. Composite grains are enforced by singular
tests under [transform/tests/](../transform/tests/) (no `dbt_utils` dependency).

## Where each runs

| Code | Imported by | Heavy deps |
| --- | --- | --- |
| `matching.py`, `categorization.py` | dbt Python models + CLI/tests | rapidfuzz, scipy (`analysis`) |
| `embeddings.py` | optional semantic categorization | fastembed (`ml`) |
