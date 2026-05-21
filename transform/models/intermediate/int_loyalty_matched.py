"""Fidélité one-to-one join (dbt-duckdb Python model).

Each loyalty line is matched to at most one receipt product *line* purchased the
same day, and each receipt line to at most one loyalty line — an optimal one-to-one
assignment (Hungarian algorithm) over a rapidfuzz string-similarity matrix. This
replaces the previous greedy SQL (`row_number` per loyalty line, which allowed the
same receipt label to be matched by several loyalty lines and dropped quantities
via `select distinct`). Logic lives in `carrefour_receipts_api.matching` and is
unit-tested.

Grain: one row per loyalty line (unchanged), plus `matched_line_id`
(receipt `line_dlt_key`, NULL when unmatched), `matched_label`, `match_similarity`.
"""


def model(dbt, session):
    dbt.config(materialized="table")

    from carrefour_receipts_api import config
    from carrefour_receipts_api.matching import match_loyalty_to_receipts

    loyalty = dbt.ref("stg_loyalty").df()
    receipt_lines = dbt.ref("stg_receipt_lines").df()

    candidates = loyalty[loyalty["item_label"].notna() & (loyalty["item_label"] != "")]
    matches = match_loyalty_to_receipts(
        candidates,
        receipt_lines,
        threshold=config.FIDELITY_MATCH_THRESHOLD,
    )

    out = loyalty.merge(matches, on="loyalty_line_id", how="left")
    # Loyalty lines with no same-day receipt (or left unassigned) get similarity 0.
    out["match_similarity"] = out["match_similarity"].fillna(0.0)
    return out
