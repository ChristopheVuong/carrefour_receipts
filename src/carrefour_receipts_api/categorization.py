"""Product-label categorization — keyword/rapidfuzz classifier (no matplotlib, no torch).

Turns a free-text product label (e.g. ``"LIQUIDE VAISSELLE 500ML"``) into a coarse
``category`` (food / hygiene_beauty / household / other) plus a finer ``subcategory``,
by fuzzy-matching the label against a small curated keyword table (the dbt seed
``seed_product_categories``).

Kept dependency-light and free of matplotlib/fastembed so the dbt-duckdb Python model
``int_product_categorized`` can import it during a normal ``dbt build`` (the ``analysis``
extra — rapidfuzz — is enough; the ``ml`` extra is *not* required). This mirrors the
isolation rationale of :mod:`carrefour_receipts_api.matching`.

The default scorer is :func:`rapidfuzz.fuzz.partial_ratio` so a short keyword matches
when it appears *inside* a longer label (``"banane"`` ⊂ ``"bananes bio"``). Matching is
fully deterministic — ties break on ``(score, priority, keyword)`` — so it is CI-safe.

An optional embeddings-based path (:func:`categorize_labels_semantic`) is provided for
local exploration; it is guarded so the absence of the ``ml`` extra never breaks a build.
"""

from __future__ import annotations

import pandas as pd
from rapidfuzz import fuzz

from carrefour_receipts_api.matching import preprocess

CATEGORIES = ("food", "hygiene_beauty", "household", "other")

_OUTPUT_COLUMNS = ["product_label", "category", "subcategory", "match_confidence"]


def categorize_labels(
    labels: pd.DataFrame,
    seed: pd.DataFrame,
    threshold: float,
    scorer=fuzz.partial_ratio,
) -> pd.DataFrame:
    """Classify distinct product labels against a keyword seed table.

    Args:
        labels: rows with a ``product_label`` column (duplicates/NA tolerated).
        seed: keyword table with columns ``keyword``, ``category``, ``subcategory``,
            ``priority`` (higher priority wins on near-ties).
        threshold: minimum similarity in [0, 1] for a keyword to classify a label;
            below it the label gets a NULL category (caller falls back, e.g. to the
            VAT heuristic).
        scorer: rapidfuzz scorer (0-100; normalized to [0, 1]). ``partial_ratio`` by
            default so a keyword matches as a substring of the label.

    Returns one row per *distinct* product label with columns ``product_label``,
    ``category``, ``subcategory``, ``match_confidence``. Deterministic: among keywords
    at/above the threshold the winner maximizes ``(score, priority)``, ties broken by
    keyword text.
    """
    uniq = labels["product_label"].dropna().astype(str).drop_duplicates().tolist()

    seed = seed.copy()
    seed["_kw"] = seed["keyword"].astype(str).map(preprocess)
    seed["priority"] = seed["priority"].fillna(0).astype(int)
    keywords = list(
        zip(
            seed["_kw"],
            seed["priority"],
            seed["category"].astype(str),
            seed["subcategory"].astype(str),
            strict=True,
        )
    )

    records: list[dict] = []
    for label in uniq:
        processed = preprocess(label)
        best: tuple[float, int, str, str] | None = None
        for kw, priority, category, subcategory in keywords:
            if not kw:
                continue
            score = scorer(kw, processed) / 100.0
            if score < threshold:
                continue
            candidate = (score, priority, category, subcategory)
            # Deterministic: higher (score, priority) wins; break ties on keyword text.
            if best is None or (score, priority) > (best[0], best[1]):
                best = candidate

        if best is not None:
            records.append(
                {
                    "product_label": label,
                    "category": best[2],
                    "subcategory": best[3],
                    "match_confidence": best[0],
                }
            )
        else:
            records.append(
                {
                    "product_label": label,
                    "category": None,
                    "subcategory": None,
                    "match_confidence": 0.0,
                }
            )

    return pd.DataFrame(records, columns=_OUTPUT_COLUMNS)


def categorize_labels_semantic(
    labels: pd.DataFrame,
    seed: pd.DataFrame,
    threshold: float,
) -> pd.DataFrame | None:
    """Embeddings-based variant (optional, local-only).

    Encodes labels and seed keywords with the fastembed ONNX encoder and assigns each
    label the category of its nearest keyword by cosine similarity. Returns ``None`` if
    the optional ``ml`` extra (fastembed) or sklearn is unavailable, so callers can fall
    back to :func:`categorize_labels` without the build ever failing in CI.
    """
    try:
        from sklearn.metrics.pairwise import cosine_similarity

        from carrefour_receipts_api.embeddings import load_encoder
    except ImportError:
        return None

    uniq = labels["product_label"].dropna().astype(str).drop_duplicates().tolist()
    if not uniq:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    seed = seed.copy()
    seed["priority"] = seed["priority"].fillna(0).astype(int)

    try:
        encoder = load_encoder()
        label_vecs = encoder.encode([preprocess(x) for x in uniq])
        kw_vecs = encoder.encode([preprocess(k) for k in seed["keyword"].astype(str)])
    except Exception:  # pragma: no cover - network/model fetch failure
        return None

    sim = cosine_similarity(label_vecs, kw_vecs)
    records: list[dict] = []
    for i, label in enumerate(uniq):
        j = int(sim[i].argmax())
        score = float(sim[i, j])
        if score >= threshold:
            row = seed.iloc[j]
            records.append(
                {
                    "product_label": label,
                    "category": str(row["category"]),
                    "subcategory": str(row["subcategory"]),
                    "match_confidence": score,
                }
            )
        else:
            records.append(
                {
                    "product_label": label,
                    "category": None,
                    "subcategory": None,
                    "match_confidence": score,
                }
            )

    return pd.DataFrame(records, columns=_OUTPUT_COLUMNS)
