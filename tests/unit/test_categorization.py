"""Unit tests for the product-label categorizer (rapidfuzz keyword matching).

The production model is the dbt Python model ``int_product_categorized``, which calls
:func:`carrefour_receipts_api.categorization.categorize_labels` against the dbt seed.
These tests pin the behaviour that matters downstream: correct category assignment,
the priority tie-break, determinism, and the threshold fallback (NULL category).
"""

import pandas as pd
import pytest

from carrefour_receipts_api.categorization import CATEGORIES, categorize_labels

# Mirrors the committed seed shape (keyword, category, subcategory, priority).
SEED = pd.DataFrame(
    [
        ("banane", "food", "fruit", 80),
        ("carotte", "food", "vegetable", 80),
        ("liquide vaisselle", "household", "dishwashing", 95),
        ("vaisselle", "household", "dishwashing", 85),
        ("dentifrice", "hygiene_beauty", "oral_care", 90),
        ("gel douche", "hygiene_beauty", "body_care", 90),
        ("essuie-tout", "household", "paper", 90),
    ],
    columns=["keyword", "category", "subcategory", "priority"],
)


def _categorize(labels, threshold=0.80):
    df = pd.DataFrame({"product_label": labels})
    return categorize_labels(df, SEED, threshold=threshold)


@pytest.mark.fast
def test_assigns_expected_categories():
    out = _categorize(
        ["BANANES BIO", "CAROTTES VRAC", "DENTIFRICE MENTHE", "GEL DOUCHE 250ML"]
    ).set_index("product_label")
    assert out.loc["BANANES BIO", "category"] == "food"
    assert out.loc["BANANES BIO", "subcategory"] == "fruit"
    assert out.loc["CAROTTES VRAC", "category"] == "food"
    assert out.loc["DENTIFRICE MENTHE", "category"] == "hygiene_beauty"
    assert out.loc["GEL DOUCHE 250ML", "subcategory"] == "body_care"


@pytest.mark.fast
def test_all_categories_are_in_the_accepted_set():
    out = _categorize(["LIQUIDE VAISSELLE 500ML", "ESSUIE-TOUT X4"])
    assert set(out["category"]) <= set(CATEGORIES)


@pytest.mark.fast
def test_priority_breaks_near_ties():
    """`liquide vaisselle` (priority 95) outranks the generic `vaisselle` (85)."""
    out = _categorize(["LIQUIDE VAISSELLE 500ML"]).iloc[0]
    assert out["category"] == "household"
    assert out["match_confidence"] >= 0.80


@pytest.mark.fast
def test_below_threshold_label_gets_null_category():
    """An unrelated label yields a NULL category (caller falls back to VAT)."""
    out = _categorize(["PILES AAA X4"]).iloc[0]
    assert out["category"] is None
    assert out["subcategory"] is None
    assert out["match_confidence"] == 0.0


@pytest.mark.fast
def test_is_deterministic_and_one_row_per_distinct_label():
    labels = ["BANANES BIO", "BANANES BIO", "CAROTTES VRAC"]
    first = _categorize(labels)
    second = _categorize(labels)
    assert len(first) == 2  # de-duplicated
    pd.testing.assert_frame_equal(first, second)
