"""Unit tests for the loyalty (fidélité) label-matching helpers.

The *production* fidélité join is the dbt Python model ``int_loyalty_matched``,
which calls :func:`carrefour_receipts_api.matching.match_loyalty_to_receipts`
(one-to-one Hungarian assignment over rapidfuzz similarity). These tests cover:

  - ``preprocess`` (diacritics / casing normalization),
  - ``fuzzy_match`` (rapidfuzz best match above a threshold),
  - ``match_loyalty_to_receipts`` (the one-to-one guarantee),
  - the fastembed semantic encoder (``slow``; skipped without the ``ml`` extra).
"""

import pandas as pd
import pytest

from carrefour_receipts_api.matching import (
    fuzzy_match,
    match_loyalty_to_receipts,
    preprocess,
)

# Loyalty label -> the receipt product label it should resolve to (mirrors the
# committed loyalty/receipt fixtures used by the dbt fidélité join).
RECEIPT_LABELS = [
    "BANANES BIO",
    "LAIT DEMI ECREME 1L",
    "LIQUIDE VAISSELLE 500ML",
    "POMMES GALA",
    "YAOURT NATURE X8",
    "DENTIFRICE MENTHE",
    "PAIN DE MIE COMPLET",
]


@pytest.mark.fast
def test_preprocess_strips_diacritics_and_lowercases():
    assert preprocess("CRÈME FRAÎCHE") == "creme fraiche"
    assert preprocess("  Éclair Café  ") == "eclair cafe"


@pytest.mark.fast
@pytest.mark.parametrize(
    "loyalty_label, expected",
    [
        ("BANANE BIO", "BANANES BIO"),
        ("LAIT DEMI-ECREME 1L", "LAIT DEMI ECREME 1L"),
        ("LIQUIDE VAISSELLE 500 ML", "LIQUIDE VAISSELLE 500ML"),
        ("POMME GALA", "POMMES GALA"),
        ("YAOURT NATURE X 8", "YAOURT NATURE X8"),
        ("PAIN MIE COMPLET", "PAIN DE MIE COMPLET"),
    ],
)
def test_fuzzy_match_resolves_loyalty_to_receipt_label(loyalty_label, expected):
    """Slightly-misspelled loyalty labels resolve to the right receipt product."""
    assert fuzzy_match(loyalty_label, RECEIPT_LABELS, processor=preprocess) == expected


@pytest.mark.fast
def test_fuzzy_match_returns_none_below_threshold():
    """An unrelated label (e.g. the aggregate fidélité line) yields no match."""
    assert (
        fuzzy_match("ART RAYON FIDELITE", RECEIPT_LABELS, processor=preprocess, threshold=80)
        is None
    )


@pytest.mark.fast
def test_match_loyalty_to_receipts_is_one_to_one():
    """Two same-day loyalty lines both closest to one receipt label must NOT both
    take it — the Hungarian assignment spreads them across distinct receipt lines."""
    loyalty = pd.DataFrame(
        {
            "loyalty_line_id": ["L1", "L2"],
            "loyalty_date": ["2024-01-15", "2024-01-15"],
            "item_label": ["BANANE BIO", "BANANE BIO"],  # identical -> would collide if greedy
        }
    )
    receipt_lines = pd.DataFrame(
        {
            "receipt_date": ["2024-01-15", "2024-01-15"],
            "line_dlt_key": ["r1", "r2"],
            "product_label": ["BANANES BIO", "BANANE BIOLOGIQUE"],
        }
    )

    result = match_loyalty_to_receipts(loyalty, receipt_lines, threshold=0.5)

    matched = result.dropna(subset=["matched_line_id"])
    assert len(matched) == 2  # both loyalty lines matched
    # one-to-one: each receipt line claimed at most once
    assert matched["matched_line_id"].nunique() == 2
    assert set(matched["matched_line_id"]) == {"r1", "r2"}


@pytest.mark.fast
def test_match_loyalty_to_receipts_respects_threshold_and_dates():
    """Below-threshold pairs and loyalty lines with no same-day receipt stay unmatched."""
    loyalty = pd.DataFrame(
        {
            "loyalty_line_id": ["L1", "L2"],
            "loyalty_date": ["2024-01-15", "2024-02-20"],  # L2 has no same-day receipt
            "item_label": ["ZZZ UNRELATED", "POMME GALA"],
        }
    )
    receipt_lines = pd.DataFrame(
        {
            "receipt_date": ["2024-01-15"],
            "line_dlt_key": ["r1"],
            "product_label": ["BANANES BIO"],
        }
    )

    result = match_loyalty_to_receipts(loyalty, receipt_lines, threshold=0.85)

    # L1 scored against r1 but below threshold -> no match; L2 absent (no same-day receipt).
    assert "L2" not in set(result["loyalty_line_id"])
    l1 = result[result["loyalty_line_id"] == "L1"]
    assert len(l1) == 1
    assert l1["matched_line_id"].isna().all()


@pytest.mark.slow
def test_encoder_semantic_similarity():
    """fastembed encoder: a near-duplicate label is closer than an unrelated one.

    Skipped when the optional ``ml`` extra (fastembed) or the model download is
    unavailable — so CI (which installs only elt + analysis) skips it cleanly.
    """
    pytest.importorskip("fastembed")
    from sklearn.metrics.pairwise import cosine_similarity

    from carrefour_receipts_api.embeddings import load_encoder

    try:
        encoder = load_encoder()
        vectors = encoder.encode(["BANANE BIO", "BANANES BIO", "LIQUIDE VAISSELLE"])
    except Exception as exc:  # pragma: no cover - network/model fetch failure
        pytest.skip(f"fastembed model unavailable: {exc}")

    sim = cosine_similarity(vectors)
    assert sim[0, 1] > sim[0, 2]  # banane~bananes closer than banane~vaisselle
