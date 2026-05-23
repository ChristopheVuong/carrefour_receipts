"""Product-label categorization (dbt-duckdb Python model).

Classifies each *distinct* product label (store receipts + Drive orders) into a coarse ``category``
(food / hygiene_beauty / household / other) and a finer ``subcategory`` by
fuzzy-matching it against the curated ``seed_product_categories`` keyword table.
Logic lives in :mod:`carrefour_receipts_api.categorization` (rapidfuzz only — no
fastembed needed) and is unit-tested.

Replaces nothing: ``fct_receipt_lines`` keeps the VAT-based binary heuristic as a
fallback (``vat_category``) and overlays this richer classification on top, so a
label below the similarity threshold still gets a sensible category.

Grain: one row per distinct ``product_label``.
"""


def model(dbt, session):
    # Materialized as a table via dbt_project.yml (intermediate: +materialized: table).
    from carrefour_receipts_api import config
    from carrefour_receipts_api.categorization import (
        categorize_labels,
        categorize_labels_semantic,
    )

    import pandas as pd

    receipt_lines = dbt.ref("stg_receipt_lines").df()
    order_lines = dbt.ref("stg_order_lines").df()
    seed = dbt.ref("seed_product_categories").df()
    # Categorize labels from both channels (store receipts + Drive orders); the
    # categorizer dedups internally, so one row per distinct label is returned.
    labels = pd.concat(
        [receipt_lines[["product_label"]], order_lines[["product_label"]]],
        ignore_index=True,
    )

    out = None
    if config.CATEGORY_USE_EMBEDDINGS:
        # Optional local-only path; returns None if the ml extra is unavailable.
        out = categorize_labels_semantic(
            labels, seed, threshold=config.CATEGORY_MATCH_THRESHOLD
        )
    if out is None:
        out = categorize_labels(labels, seed, threshold=config.CATEGORY_MATCH_THRESHOLD)

    return out
