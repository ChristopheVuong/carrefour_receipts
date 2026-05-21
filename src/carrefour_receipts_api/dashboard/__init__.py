"""Streamlit analytics dashboard over the DuckDB marts.

Run locally with ``make dashboard`` (or ``streamlit run
src/carrefour_receipts_api/dashboard/app.py``), or via Docker — see
``docs/dashboard.md``. The app reads the dbt-built marts (``mart_monthly_spend``,
``mart_category_insights``, ``mart_product_prices``, ``mart_quantities``) from the
DuckDB file at ``config.DUCKDB_PATH``; build them first with ``make build``.
"""
