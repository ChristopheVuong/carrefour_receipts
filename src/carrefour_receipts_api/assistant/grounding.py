"""Build the assistant's grounding context (the "schema card") from dbt + DuckDB.

Vanna 2.0 has no ``vn.train()``; instead we inject the schema as the agent's **system
prompt**. The card describes the queryable analytical layer (facts/dims/intermediate/
marts) — table grains + column types (live DuckDB introspection) + column descriptions
(dbt ``manifest.json``) — plus a handful of curated question→SQL examples that act as a
lightweight semantic layer for the most common financial questions.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from carrefour_receipts_api import config
from carrefour_receipts_api.assistant.sql_guard import ALLOWED_TABLE_PREFIXES

_MANIFEST_PATH = Path("transform/target/manifest.json")

# Curated question → SQL examples (few-shot). They double as a semantic layer for the
# common financial questions and show the model the marts (pre-aggregated) AND the facts
# (ad-hoc aggregation at line/receipt/day grain). Keep these aligned with the marts.
EXAMPLE_QUERIES: list[tuple[str, str]] = [
    (
        "Combien ai-je dépensé par catégorie cette année ?",
        "select category, round(sum(spend), 2) as spend\n"
        "from main.mart_category_insights\n"
        "where year_month >= strftime(date_trunc('year', current_date), '%Y-%m')\n"
        "group by 1 order by spend desc",
    ),
    (
        "Magasin vs Drive : combien sur chaque canal au total ?",
        "select channel, round(sum(total_paid), 2) as total_paid\n"
        "from main.mart_monthly_spend group by 1 order by total_paid desc",
    ),
    (
        "Combien la cagnotte fidélité m'a fait gagner cette année ?",
        "select round(sum(loyalty_savings), 2) as cagnotte_gagnee\n"
        "from main.mart_loyalty_savings\n"
        "where year_month >= strftime(date_trunc('year', current_date), '%Y-%m')",
    ),
    (
        "Quelle réduction immédiate ai-je eue mois par mois ?",
        "select year_month, round(sum(immediate_discount), 2) as reduction_immediate\n"
        "from main.mart_monthly_spend group by 1 order by year_month",
    ),
    (
        "Mes courses jour par jour ce mois-ci (ad-hoc sur les faits)",
        "select purchase_date, round(sum(total_paid), 2) as paid\n"
        "from main.int_purchases\n"
        "where strftime(purchase_date, '%Y-%m') = strftime(current_date, '%Y-%m')\n"
        "group by 1 order by purchase_date",
    ),
    (
        "Top 10 des produits les plus achetés (quantité)",
        "select product_label, round(sum(quantity), 2) as quantity\n"
        "from main.int_purchase_lines\n"
        "group by 1 order by quantity desc limit 10",
    ),
    (
        "Évolution du prix moyen du lait",
        "select year_month, channel, round(avg_unit_price, 2) as avg_unit_price\n"
        "from main.mart_product_prices\n"
        "where product_label ilike '%lait%' order by year_month",
    ),
]


def _load_manifest_descriptions(manifest_path: Path) -> dict[str, dict[str, object]]:
    """Return ``{table_name: {"description": str, "columns": {col: desc}}}`` from dbt."""
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, object]] = {}
    for node in manifest.get("nodes", {}).values():
        if node.get("resource_type") != "model" or node.get("schema") != "main":
            continue
        cols = {c: (v.get("description") or "") for c, v in (node.get("columns") or {}).items()}
        out[node["name"]] = {"description": node.get("description") or "", "columns": cols}
    return out


def _allowed_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Names of ``main`` tables/views in the analytical-layer allowlist, sorted."""
    rows = con.execute(
        "select table_name from information_schema.tables where table_schema = 'main' "
        "order by table_name"
    ).fetchall()
    return [r[0] for r in rows if r[0].startswith(ALLOWED_TABLE_PREFIXES)]


def schema_card(db_path: str | None = None, manifest_path: Path | None = None) -> str:
    """Build the system-prompt schema card for the queryable analytical layer."""
    db_path = db_path or config.DUCKDB_PATH
    descriptions = _load_manifest_descriptions(manifest_path or _MANIFEST_PATH)

    lines: list[str] = [
        "You are a careful financial data analyst for a household's Carrefour grocery "
        "spending (in-store receipts + online Drive orders + loyalty/fidélité).",
        "",
        "Queryable tables (DuckDB schema `main`). Use ONLY these; never query raw.* or "
        "stg_* tables. The marts are pre-aggregated (fast); the fct_*/int_* facts allow "
        "ad-hoc aggregation at line/receipt/day grain. Amounts are euros; `channel` is "
        "'store' or 'drive'.",
        "",
    ]

    con = duckdb.connect(db_path, read_only=True)
    try:
        for table in _allowed_tables(con):
            meta = descriptions.get(table, {})
            desc = str(meta.get("description") or "").strip()
            col_desc_raw = meta.get("columns") or {}
            col_desc: dict[str, object] = col_desc_raw if isinstance(col_desc_raw, dict) else {}
            lines.append(f"### main.{table}" + (f" — {desc}" if desc else ""))
            cols = con.execute(
                "select column_name, data_type from information_schema.columns "
                "where table_schema = 'main' and table_name = ? order by ordinal_position",
                [table],
            ).fetchall()
            for col_name, col_type in cols:
                cd = str(col_desc.get(col_name, "")).strip()
                lines.append(f"- {col_name} ({col_type})" + (f": {cd}" if cd else ""))
            lines.append("")
    finally:
        con.close()

    lines.append("Example questions and the SQL that answers them:")
    for question, sql in EXAMPLE_QUERIES:
        lines.append(f"\nQ: {question}\nSQL:\n{sql}")
    return "\n".join(lines)
