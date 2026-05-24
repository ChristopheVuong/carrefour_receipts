"""Streamlit dashboard for Carrefour receipt analytics.

Reads the dbt-built marts from the DuckDB file and renders interactive spend,
category, price and quantity views. Build the marts first (``make build``).

Launch: ``streamlit run src/carrefour_receipts_api/dashboard/dashboard.py`` (or ``make dashboard``).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from carrefour_receipts_api import config


def _last_extraction_date() -> str | None:
    """Return the most recent YYYYMMDD extraction folder date, or None if absent."""
    data_dir = Path(config.DATA_DIRECTORY)
    if not data_dir.exists():
        return None
    pattern = re.compile(r"^\d{8}$")
    dates = sorted(
        (p.name for p in data_dir.iterdir() if p.is_dir() and pattern.match(p.name)),
        reverse=True,
    )
    if not dates:
        return None
    raw = dates[0]
    dt = datetime.strptime(raw, "%Y%m%d")
    mois = [
        "",
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    return f"{dt.day} {mois[dt.month]} {dt.year}"


MARTS = {
    "monthly_spend": "mart_monthly_spend",
    "category_insights": "mart_category_insights",
    "product_prices": "mart_product_prices",
    "quantities": "mart_quantities",
    "loyalty_savings": "mart_loyalty_savings",
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


def _collapse_channel(df: pd.DataFrame, group_keys: list[str], channel: str) -> pd.DataFrame:
    """Scope a channel-grained mart to one channel, or sum across channels for "All".

    Sums are valid for the additive metrics here (totals, counts, kilograms) and for
    the rolling *averages* too: an average over a fixed window is linear, so the sum of
    per-channel rolling averages equals the combined rolling average.
    """
    if df.empty or "channel" not in df.columns:
        return df
    if channel != "All":
        return df[df["channel"] == channel].drop(columns=["channel"])
    numeric = df.select_dtypes("number").columns.tolist()
    keys = [k for k in group_keys if k in df.columns]
    return df.groupby(keys, as_index=False, dropna=False)[numeric].sum()


def _collapse_prices(df: pd.DataFrame, channel: str) -> pd.DataFrame:
    """Per-product price view: filter to a channel, or quantity-weight across channels."""
    if df.empty or "channel" not in df.columns:
        return df
    if channel != "All":
        return df[df["channel"] == channel].drop(columns=["channel"])
    work = df.copy()
    work["_weighted"] = work["avg_unit_price"] * work["quantity"]
    grouped = work.groupby(
        ["product_label", "subcategory", "year_month"], as_index=False, dropna=False
    ).agg(
        _weighted=("_weighted", "sum"),
        quantity=("quantity", "sum"),
        line_count=("line_count", "sum"),
        total_quantity=("total_quantity", "max"),
    )
    grouped["avg_unit_price"] = grouped["_weighted"] / grouped["quantity"].replace(0, pd.NA)
    grouped["is_top_product"] = grouped["total_quantity"] >= 5
    return grouped.drop(columns=["_weighted"])


def main() -> None:
    st.set_page_config(page_title="Dashboard Carrefour", page_icon="🧾", layout="wide")
    st.title("🧾 Dashboard — Courses Carrefour")

    db_path = config.DUCKDB_PATH
    spend = load_mart(MARTS["monthly_spend"], db_path)

    if spend.empty:
        st.warning(
            f"Aucune donnée dans `{db_path}`. Lance d'abord `make build` "
            "(dlt load + dbt build), puis recharge la page."
        )
        st.stop()

    categories = load_mart(MARTS["category_insights"], db_path)
    prices = load_mart(MARTS["product_prices"], db_path)
    quantities = load_mart(MARTS["quantities"], db_path)
    loyalty = load_mart(MARTS["loyalty_savings"], db_path)

    # --- Filtres latéraux ---------------------------------------------------
    all_months = sorted(spend["year_month"].dropna().unique().tolist())
    all_years = sorted({int(m[:4]) for m in all_months})
    cat_values = (
        sorted(categories["category"].dropna().unique().tolist()) if not categories.empty else []
    )

    channel_values = (
        sorted(spend["channel"].dropna().unique().tolist()) if "channel" in spend else []
    )

    st.sidebar.header("Filtres")
    # Store English sentinel internally so helper functions stay channel-value agnostic.
    _channel_label = st.sidebar.selectbox("Canal", ["Tous", *channel_values])
    sel_channel = "All" if _channel_label == "Tous" else _channel_label
    sel_years = st.sidebar.multiselect("Année", all_years, default=all_years)
    sel_months = st.sidebar.multiselect("Mois", all_months, default=all_months)
    sel_cats = st.sidebar.multiselect("Catégorie", cat_values, default=cat_values)

    st.sidebar.divider()
    last_date = _last_extraction_date()
    if last_date:
        st.sidebar.caption(f"Dernière extraction : **{last_date}**")
    else:
        st.sidebar.caption("Dernière extraction : inconnue")

    spend_f = _filter_year_month(
        _collapse_channel(spend, ["year_month", "year", "month"], sel_channel),
        sel_years,
        sel_months,
    )

    # Loyalty (fidélité) savings are the store programme only — no Drive, no channel.
    loyalty_f = _filter_year_month(loyalty, sel_years, sel_months) if not loyalty.empty else loyalty
    loyalty_earned = (
        0.0
        if sel_channel == "drive" or loyalty_f.empty
        else float(loyalty_f["loyalty_savings"].sum())
    )

    # --- KPI headline -------------------------------------------------------
    gross = spend_f["total_before_immediate_discount"].sum()
    immediate = spend_f["immediate_discount"].sum()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total payé (net)", f"€{spend_f['total_paid'].sum():,.2f}")
    c2.metric("Avant remise immédiate", f"€{gross:,.2f}")
    c3.metric("Remise immédiate", f"€{immediate:,.2f}")
    c4.metric("Cagnotte fidélité gagnée", f"€{loyalty_earned:,.2f}")
    c5.metric("Achats", int(spend_f["purchase_count"].sum()))

    # --- Dépenses mensuelles + moyenne glissante ----------------------------
    st.subheader("Dépenses mensuelles")
    spend_long = spend_f.melt(
        id_vars="year_month",
        value_vars=[
            c
            for c in ("total_before_immediate_discount", "total_paid", "total_paid_roll_3m")
            if c in spend_f
        ],
        var_name="series",
        value_name="amount",
    )
    st.line_chart(spend_long, x="year_month", y="amount", color="series")

    # --- Économies : remise immédiate + cagnotte fidélité -------------------
    st.subheader("Économies (remise immédiate + cagnotte fidélité)")
    savings = spend_f.groupby("year_month", as_index=False)[["immediate_discount"]].sum()
    if not loyalty_f.empty:
        savings = savings.merge(
            loyalty_f[["year_month", "loyalty_savings"]], on="year_month", how="outer"
        )
    savings = savings.fillna(0.0).sort_values("year_month")
    value_vars = [c for c in ("immediate_discount", "loyalty_savings") if c in savings]
    savings_long = savings.melt(
        id_vars="year_month", value_vars=value_vars, var_name="kind", value_name="amount"
    )
    st.bar_chart(savings_long, x="year_month", y="amount", color="kind")
    st.caption(
        "La cagnotte fidélité correspond au programme en magasin (points + remises produits) ; "
        "elle est indépendante du filtre canal."
    )

    # --- Répartition par catégorie ------------------------------------------
    if not categories.empty:
        st.subheader("Dépenses par catégorie")
        cat_f = _filter_year_month(
            _collapse_channel(categories, ["year_month", "category"], sel_channel),
            sel_years,
            sel_months,
        )
        if sel_cats:
            cat_f = cat_f[cat_f["category"].isin(sel_cats)]
        st.bar_chart(cat_f, x="year_month", y="spend", color="category")

    # --- Tendances de prix produit ------------------------------------------
    if not prices.empty:
        st.subheader("Évolution du prix unitaire par produit")
        prices_c = _collapse_prices(prices, sel_channel)
        top = prices_c[prices_c["is_top_product"]] if "is_top_product" in prices_c else prices_c
        products = sorted(top["product_label"].dropna().unique().tolist())
        chosen = st.multiselect("Produits", products, default=products[:5])
        price_f = _filter_year_month(top[top["product_label"].isin(chosen)], sel_years, sel_months)
        if not price_f.empty:
            st.line_chart(price_f, x="year_month", y="avg_unit_price", color="product_label")

    # --- Quantités ----------------------------------------------------------
    if not quantities.empty:
        st.subheader("Quantités")
        qty_f = _filter_year_month(
            _collapse_channel(quantities, ["year_month"], sel_channel), sel_years, sel_months
        )
        st.bar_chart(qty_f, x="year_month", y=["fruit_veg_kg", "total_items"])


if __name__ == "__main__":
    main()
