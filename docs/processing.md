# Processing & matching

The Python processing layer holds the analytical logic that doesn't belong in SQL — fuzzy
matching, embeddings, categorization. The two matching/categorization primitives are
imported by the dbt **Python models**, so they are kept free of heavy/plotting dependencies.

## Fidélité one-to-one matching — [matching.py](../src/carrefour_receipts_api/matching.py)

Matches loyalty item labels to receipt product lines on the same day.

- `preprocess(text)` — lowercase + strip diacritics; used as the fuzzy processor.
- `match_loyalty_to_receipts(loyalty, receipt_lines, threshold, scorer=fuzz.WRatio)` —
  builds a rapidfuzz similarity matrix per day (`process.cdist`) and solves an **optimal
  one-to-one assignment** with the Hungarian algorithm
  (`scipy.optimize.linear_sum_assignment`, via `find_maximum_similarity_matching`). Each
  loyalty line maps to at most one receipt line and vice versa; pairs below `threshold`
  stay unmatched.

Used by the dbt model `int_loyalty_matched`. Threshold: `config.FIDELITY_MATCH_THRESHOLD`
(env `FIDELITY_MATCH_THRESHOLD`, default 0.85). No matplotlib so dbt can import it.

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

## ELT — Loyalty merge & line key

**Load grain (dlt):** the loyalty extract is one JSON document **per month** (`_id` = `YYYYMM`)
carrying a `history` array. dlt unnests `history` into the child table `raw.loyalty__history`,
and the `loyalty` resource `merge`s on the month `_id`
([elt/load.py](../src/carrefour_receipts_api/elt/load.py)). So reloading a month replaces its
lines while older months (absent from a fresh ~1-year extract) are kept — DuckDB **accumulates**
history across loads, necessary because the API only returns a rolling ~1-year window (see
[api-extraction.md](api-extraction.md)).

**Line key (dbt):** a loyalty line has no natural key (`operationId` repeats across an
operation's items; dlt's `_dlt_id` changes every load), so `stg_loyalty` derives a deterministic
`loyalty_line_id = md5(signature | occurrence)` from the unnested rows: the signature (all
business fields, amounts rounded so `0.10` == `0.1`) plus a `row_number()` occurrence keeps
genuinely duplicate lines distinct. Same content always yields the same key, so it is stable
across rebuilds.

> **Migration caveat:** the line key is recomputed by dbt each build (not stored). Changing the
> signature columns in [stg_loyalty.sql](../transform/models/staging/stg_loyalty.sql) changes
> every `loyalty_line_id` — harmless on a full `make build`, but anything that pinned old keys
> must be rebuilt.

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
