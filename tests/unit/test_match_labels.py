"""Unit tests for the label-matching helpers.

``preprocess`` is the shared rapidfuzz processor used by the product categorization
model; ``fuzzy_match`` is the generic best-match helper. These tests cover:

  - ``preprocess`` (diacritics / casing normalization),
  - ``fuzzy_match`` (rapidfuzz best match above a threshold),
  - the fastembed semantic encoder (``slow``; skipped without the ``ml`` extra).
"""

import pytest

from carrefour_receipts_api.matching import fuzzy_match, preprocess

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
