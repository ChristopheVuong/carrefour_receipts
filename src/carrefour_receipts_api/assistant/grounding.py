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
        "Tu es un analyste financier rigoureux qui aide un foyer à comprendre ses dépenses "
        "de courses Carrefour (tickets en magasin + commandes Drive en ligne + fidélité/"
        "cagnotte).",
        "",
        "RÉPONDS TOUJOURS EN FRANÇAIS. Montants en euros (€), dates au format français. Sois "
        "concis : une réponse chiffrée et claire, sans recopier le SQL ni les lignes brutes.",
        "",
        "Dialecte SQL : DuckDB. Tables interrogeables (schéma `main`). N'utilise QUE "
        "celles-ci ; ne requête jamais les tables raw.* ou stg_*. Les marts sont "
        "pré-agrégées (rapides) ; les faits fct_*/int_* permettent une agrégation ad-hoc au "
        "grain ligne/ticket/jour. `channel` vaut 'store' (magasin) ou 'drive'.",
        "",
        "MÉTHODE — pour chaque question :",
        "1. Appelle l'outil `run_sql` avec une requête SELECT (lecture seule).",
        "2. Si la question implique une tendance, une évolution dans le temps, une "
        "comparaison entre catégories/canaux, ou une répartition, enchaîne avec l'outil "
        "`visualize_data` en passant le `filename` CSV renvoyé par `run_sql` (un graphique "
        "vaut mieux qu'un tableau pour ces cas). Sinon, un tableau suffit.",
        "3. Termine par une courte synthèse en français répondant directement à la question.",
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
