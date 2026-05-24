"""Extract-Load layer of the modern data stack.

Replaces the bespoke ``pymongo`` insertion + MongoDB aggregation pipelines with
``dlt`` loading raw receipt JSON into DuckDB. dlt auto-normalizes the nested
documents (``products``, ``vats``, ``paymentInfo`` become child tables) and
performs idempotent ``merge`` loads keyed on the receipt ``id`` — so re-running
the loader never produces duplicates. Transformation then happens in dbt (SQL).
"""

from carrefour_receipts_api.elt.load import load_all, load_loyalty, load_receipts

__all__ = ["load_all", "load_loyalty", "load_receipts"]
