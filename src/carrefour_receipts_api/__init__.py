# src/__init__.py
"""
carrefour_receipts_api: extract, model and analyze personal Carrefour receipts.

Modules:
    elt: dlt extract-load of receipts + loyalty JSON/CSV into DuckDB.
    matching: label-matching primitives for the fidélité one-to-one join.
    embeddings: fastembed (ONNX) text encoder for semantic label matching.
    user_api_extractor: classes to fetch data from the Carrefour API endpoints.
"""
name = "carrefour_receipts_api"