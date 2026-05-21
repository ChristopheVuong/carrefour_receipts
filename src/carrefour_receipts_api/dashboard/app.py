"""Streamlit dashboard for Carrefour receipt analytics.

Reads the dbt-built marts from the DuckDB file and renders interactive spend,
category, price and quantity views. Build the marts first (``make build``).

Launch: ``streamlit run src/carrefour_receipts_api/dashboard/app.py`` (or ``make dashboard``).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from carrefour_receipts_api import config

MARTS = {
    "monthly_spend": "mart_monthly_spend",
    "category_insights": "mart_category_insights",
    "product_prices": "mart_product_prices",
    "quantities": "mart_quantities",
}


@st.cache_data(show_spinner=False)
def load_mart(name: str, db_path: str, schema: str = "main") -> pd.DataFrame:
    """Load one mart into a DataFrame (cached). Empty frame if the table is absent."""
    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.sql(f"select * from {schema}.{name}").df()
    except duckdb.CatalogException:
        return pd.DataFrame()
    finally:
        con.close()


def _filter_year_month(df: pd.DataFrame, years: list[int], months: list[str]) -> pd.DataFrame:
    out = df
    if "year_month" in out.columns and months:
        out = out[out["year_month"].isin(months)]
    if years and "year_month" in out.columns:
        out = out[out["year_month"].str.slice(0, 4).astype(int).isin(years)]
    return out


def main() -> None:
    st.set_page_config(page_title="Carrefour Receipts", page_icon="🧾", layout="wide")
    st.title("🧾 Carrefour Receipts — Analytics")

    db_path = config.DUCKDB_PATH
    spend = load_mart(MARTS["monthly_spend"], db_path)

    if spend.empty:
        st.warning(
            f"No marts found in `{db_path}`. Build them first with `make build` "
            "(dlt load + dbt build), then reload."
        )
        st.stop()

    categories = load_mart(MARTS["category_insights"], db_path)
    prices = load_mart(MARTS["product_prices"], db_path)
    quantities = load_mart(MARTS["quantities"], db_path)

    # --- Sidebar filters ----------------------------------------------------
    all_months = sorted(spend["year_month"].dropna().unique().tolist())
    all_years = sorted({int(m[:4]) for m in all_months})
    cat_values = (
        sorted(categories["category"].dropna().unique().tolist()) if not categories.empty else []
    )

    st.sidebar.header("Filters")
    sel_years = st.sidebar.multiselect("Year", all_years, default=all_years)
    sel_months = st.sidebar.multiselect("Month", all_months, default=all_months)
    sel_cats = st.sidebar.multiselect("Category", cat_values, default=cat_values)

    spend_f = _filter_year_month(spend, sel_years, sel_months)

    # --- KPI headline -------------------------------------------------------
    c1, c2, c3 = st.columns(3)
    c1.metric("Total paid", f"€{spend_f['total_paid'].sum():,.2f}")
    c2.metric("Immediate discount", f"€{spend_f['immediate_discount'].sum():,.2f}")
    c3.metric("Receipts", int(spend_f["receipt_count"].sum()))

    # --- Monthly spend + rolling average ------------------------------------
    st.subheader("Monthly spend")
    spend_long = spend_f.melt(
        id_vars="year_month",
        value_vars=[c for c in ("total_paid", "total_paid_roll_3m") if c in spend_f],
        var_name="series",
        value_name="amount",
    )
    st.line_chart(spend_long, x="year_month", y="amount", color="series")

    # --- Category breakdown -------------------------------------------------
    if not categories.empty:
        st.subheader("Spend by category")
        cat_f = _filter_year_month(categories, sel_years, sel_months)
        if sel_cats:
            cat_f = cat_f[cat_f["category"].isin(sel_cats)]
        st.bar_chart(cat_f, x="year_month", y="spend", color="category")

    # --- Product price trends ----------------------------------------------
    if not prices.empty:
        st.subheader("Product unit-price trends")
        top = prices[prices["is_top_product"]] if "is_top_product" in prices else prices
        products = sorted(top["product_label"].dropna().unique().tolist())
        chosen = st.multiselect("Products", products, default=products[:5])
        price_f = _filter_year_month(top[top["product_label"].isin(chosen)], sel_years, sel_months)
        if not price_f.empty:
            st.line_chart(price_f, x="year_month", y="avg_unit_price", color="product_label")

    # --- Quantities ---------------------------------------------------------
    if not quantities.empty:
        st.subheader("Quantities")
        qty_f = _filter_year_month(quantities, sel_years, sel_months)
        st.bar_chart(qty_f, x="year_month", y=["fruit_veg_kg", "total_items"])


if __name__ == "__main__":
    main()
