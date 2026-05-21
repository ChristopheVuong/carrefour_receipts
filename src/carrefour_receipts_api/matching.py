"""Label-matching primitives for the loyalty (fidélité) join — no matplotlib.

Isolated from :mod:`carrefour_receipts_api.utils` (which imports matplotlib at
module load) so the dbt-duckdb Python model `int_loyalty_matched` can import the
matching logic without dragging plotting deps into the dbt run.

The high-level entry point is :func:`match_loyalty_to_receipts`, which performs a
true **one-to-one** assignment (Hungarian algorithm, :func:`scipy.optimize.linear_sum_assignment`)
between loyalty item labels and receipt product lines on the same day, scored with
rapidfuzz string similarity. This reproduces the legacy pandas/Hungarian matching
deterministically (CI-safe, no model download).
"""

from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from scipy.optimize import linear_sum_assignment


def preprocess(text: str) -> str:
    """Lowercase and strip diacritics (NFKD) — used as the fuzzy-match processor."""
    text = text.lower()
    nfkd_form = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return text.strip()


def fuzzy_match(
    row: pd.Series, choices: list[str], scorer=fuzz.WRatio, processor=None, threshold=80
):
    """Best fuzzy match of ``row`` among ``choices`` above ``threshold`` (else None)."""
    result = process.extractOne(
        row, choices, scorer=scorer, processor=processor, score_cutoff=threshold
    )
    return result[0] if result is not None else None


def find_best_pairings_one_by_one(
    similarity_matrix,
) -> tuple[list[int], list[int], list[int], list[int], list[int], list[int]]:
    """Greedy heuristic: repeatedly take the globally highest-similarity available pair.

    Returns best and second-best pairings between group1 (rows) and group2 (cols).
    Kept as a lighter-weight alternative to the Hungarian assignment.
    """
    num_rows, num_cols = similarity_matrix.shape

    similarity_list = [
        (similarity_matrix[i, j], i, j) for i in range(num_rows) for j in range(num_cols)
    ]
    similarity_list.sort(reverse=True, key=lambda x: x[0])

    row_ind: list[int] = []
    col_ind: list[int] = []
    best_similarity_scores: list[int] = []
    row_ind2: list[int] = []
    col_ind2: list[int] = []
    second_best_similarity_scores: list[int] = []
    used_group1_indices: dict[int, int] = {}
    used_group2_indices: dict[int, int] = {}

    for similarity_score, group1_idx, group2_idx in similarity_list:
        if (
            used_group1_indices.get(group1_idx, 0) == 0
            and used_group2_indices.get(group2_idx, 0) == 0
        ):
            row_ind.append(group1_idx)
            col_ind.append(group2_idx)
            best_similarity_scores.append(similarity_score)
            used_group1_indices[group1_idx] = 1 + used_group1_indices.get(group1_idx, 0)
            used_group2_indices[group2_idx] = 1 + used_group2_indices.get(group2_idx, 0)
        else:
            if (
                used_group1_indices.get(group1_idx, 0) < 2
                and used_group2_indices.get(group2_idx, 0) < 2
            ):
                row_ind2.append(group1_idx)
                col_ind2.append(group2_idx)
                second_best_similarity_scores.append(similarity_score)
                used_group1_indices[group1_idx] = 2 + used_group1_indices.get(group1_idx, 0)
                used_group2_indices[group2_idx] = 2 + used_group2_indices.get(group2_idx, 0)

            if len(row_ind) == num_rows:
                break

    return (
        row_ind,
        col_ind,
        row_ind2,
        col_ind2,
        best_similarity_scores,
        second_best_similarity_scores,
    )


def find_maximum_similarity_matching(similarity_matrix):
    """Optimal one-to-one matching maximizing total similarity (Hungarian algorithm).

    ``linear_sum_assignment`` guarantees each row is matched to at most one column
    and vice versa (size mismatch leaves the surplus unmatched). Also returns a
    second-best assignment by penalizing the optimal edges.
    """
    cost_matrix = -similarity_matrix
    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    penalty = 1e9  # Large penalty to avoid reusing the same edges
    for i, j in zip(row_ind, col_ind, strict=False):
        cost_matrix[i][j] += penalty

    row_ind2, col_ind2 = linear_sum_assignment(cost_matrix)

    best_similarity_scores = [
        similarity_matrix[i][j] for i, j in zip(row_ind, col_ind, strict=False)
    ]
    second_best_similarity_scores = [
        similarity_matrix[i][j] for i, j in zip(row_ind2, col_ind2, strict=False)
    ]

    return (
        row_ind,
        col_ind,
        row_ind2,
        col_ind2,
        best_similarity_scores,
        second_best_similarity_scores,
    )


def match_loyalty_to_receipts(
    loyalty: pd.DataFrame,
    receipt_lines: pd.DataFrame,
    threshold: float,
    scorer=fuzz.WRatio,
) -> pd.DataFrame:
    """One-to-one match loyalty items to receipt product lines on the same day.

    Args:
        loyalty: rows with ``loyalty_line_id``, ``loyalty_date``, ``item_label``.
        receipt_lines: rows with ``receipt_date``, ``line_dlt_key``, ``product_label``
            (line grain — quantities preserved as repeated rows).
        threshold: minimum similarity in [0, 1] for a pair to count as matched.
        scorer: rapidfuzz scorer (0-100; normalized to [0, 1]).

    Returns one row per *assigned* loyalty line with columns ``loyalty_line_id``,
    ``matched_line_id``, ``matched_label``, ``match_similarity``. Within each day the
    Hungarian algorithm guarantees each loyalty line and each receipt line is used at
    most once. Pairs below ``threshold`` keep their similarity but have a NULL match.
    Loyalty lines with no same-day receipt (or left unassigned by size mismatch) are
    simply absent — callers left-join them back.
    """
    records: list[dict] = []
    receipts_by_date = dict(tuple(receipt_lines.groupby("receipt_date")))

    for date, loy_group in loyalty.groupby("loyalty_date"):
        rec_group = receipts_by_date.get(date)
        if rec_group is None or rec_group.empty:
            continue

        loy_labels = loy_group["item_label"].astype(str).tolist()
        rec_labels = rec_group["product_label"].astype(str).tolist()
        loy_ids = loy_group["loyalty_line_id"].tolist()
        rec_ids = rec_group["line_dlt_key"].tolist()

        sim = process.cdist(loy_labels, rec_labels, scorer=scorer, processor=preprocess) / 100.0
        row_ind, col_ind, *_ = find_maximum_similarity_matching(np.asarray(sim))

        for i, j in zip(row_ind, col_ind, strict=False):
            score = float(sim[i, j])
            matched = score >= threshold
            records.append(
                {
                    "loyalty_line_id": loy_ids[i],
                    "matched_line_id": rec_ids[j] if matched else None,
                    "matched_label": rec_labels[j] if matched else None,
                    "match_similarity": score,
                }
            )

    return pd.DataFrame(
        records,
        columns=["loyalty_line_id", "matched_line_id", "matched_label", "match_similarity"],
    )
