"""Label-matching primitives — no matplotlib.

Isolated from :mod:`carrefour_receipts_api.utils` (which imports matplotlib at module
load) so the dbt-duckdb Python model `int_product_categorized` can import the matching
helpers without dragging plotting deps into the dbt run. ``preprocess`` is the shared
rapidfuzz processor used by the categorization model.
"""

from __future__ import annotations

import unicodedata

import pandas as pd
from rapidfuzz import fuzz, process


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
