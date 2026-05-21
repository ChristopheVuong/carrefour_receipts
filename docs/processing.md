---
noteId: "726ec840555511f19bb6f1faf66f1118"
tags: []

---

# Processing & matching

The Python processing layer holds the analytical logic that doesn't belong in SQL — fuzzy
matching, embeddings, categorization — plus the legacy pandas exploration. The two
matching/categorization primitives are imported by the dbt **Python models**, so they are
kept free of heavy/plotting dependencies.

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

## Pandas exploration — [pandas_postprocessing.py](../src/carrefour_receipts_api/pandas_postprocessing.py)

The original notebook-style analysis: `main_matching(date)` computes label embeddings and
matches loyalty items to products; `main_merging(date)` allocates loyalty/shelf discounts
to products and derives a "true" unit price. Kept for ad-hoc exploration — the production
fidélité join is the dbt model. `pandas_postprocessing_advanced.py` holds a torch-based
cosine variant (least used).

## Where each runs

| Code | Imported by | Heavy deps |
| --- | --- | --- |
| `matching.py`, `categorization.py` | dbt Python models + CLI/tests | rapidfuzz, scipy (`analysis`) |
| `embeddings.py` | pandas exploration, optional semantic categorization | fastembed (`ml`) |
| `pandas_postprocessing*.py` | manual / notebooks | matplotlib, sklearn, fastembed |
