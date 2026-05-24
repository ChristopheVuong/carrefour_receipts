"""Read-only SQL guardrail for the assistant (sqlglot only — no vanna/duckdb import).

The LLM-generated SQL is parsed and rejected unless it is a **single read-only query**
(``SELECT`` / set operation) over the **analytical layer** (``main`` schema, tables named
``fct_* / dim_* / int_* / mart_*``). This blocks writes/DDL, multi-statements, the raw PII
tables (``raw.*``, ``stg_*`` which exposes the loyalty card number) and DuckDB file-reading
functions (``read_csv``/``read_parquet``/… could exfiltrate arbitrary files even on a
read-only connection). It is defense-in-depth alongside the read-only DuckDB connection.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

# Tables the assistant may query: the modelled analytical layer (never raw/stg).
ALLOWED_TABLE_PREFIXES: tuple[str, ...] = ("fct_", "dim_", "int_", "mart_")
ALLOWED_SCHEMAS: frozenset[str | None] = frozenset({"main", None})  # None = unqualified
# Top-level statement types that are pure reads.
_READ_TYPES = (exp.Select, exp.Union, exp.Intersect, exp.Except)
# Statement/clause types that mutate or run side effects — rejected anywhere in the tree.
_FORBIDDEN_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,  # PRAGMA / ATTACH / CALL / SET / COPY ... parse here in DuckDB
    exp.Copy,
)
# DuckDB functions that read the filesystem (would bypass the table allowlist).
_FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset(
    {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "parquet_scan",
        "read_json",
        "read_json_auto",
        "read_ndjson",
        "read_text",
        "read_blob",
        "glob",
        "sniff_csv",
    }
)


class UnsafeSqlError(ValueError):
    """Raised when generated SQL is not a permitted read-only analytical query."""


def validate_read_only_sql(sql: str) -> str:
    """Return ``sql`` unchanged if it is a safe read-only analytical query, else raise.

    Raises ``UnsafeSqlError`` for: parse errors, multiple statements, non-SELECT
    statements, write/DDL nodes, file-reading functions, or tables outside the
    ``main.{fct_,dim_,int_,mart_}`` allowlist.
    """
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as exc:  # pragma: no cover - message varies
        raise UnsafeSqlError(f"SQL invalide : {exc}") from exc

    if len(statements) != 1:
        raise UnsafeSqlError("Une seule requête est autorisée (pas de multi-instructions).")

    stmt = statements[0]
    # Unwrap a parenthesised / sub-select top level: (SELECT ...).
    while isinstance(stmt, (exp.Paren, exp.Subquery)) and stmt.this is not None:
        stmt = stmt.this

    if not isinstance(stmt, _READ_TYPES):
        raise UnsafeSqlError(
            f"Seules les requêtes SELECT sont autorisées (reçu : {type(stmt).__name__})."
        )

    for forbidden in _FORBIDDEN_TYPES:
        if stmt.find(forbidden) is not None:
            raise UnsafeSqlError("Instruction d'écriture/DDL interdite.")

    for func in stmt.find_all(exp.Anonymous):
        if (func.name or "").lower() in _FORBIDDEN_FUNCTIONS:
            raise UnsafeSqlError(f"Fonction de lecture de fichier interdite : {func.name}.")

    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    for table in stmt.find_all(exp.Table):
        name = (table.name or "").lower()
        schema = (table.db or "").lower() or None
        if schema is None and name in cte_names:
            continue  # reference to a CTE defined in the same query
        if schema not in ALLOWED_SCHEMAS:
            raise UnsafeSqlError(
                f"Schéma non autorisé : '{schema}'. Seul le schéma 'main' (marts) est permis."
            )
        if not name.startswith(ALLOWED_TABLE_PREFIXES):
            raise UnsafeSqlError(
                f"Table non autorisée : '{table.sql(dialect='duckdb')}'. "
                "Seules les tables main.{fct_,dim_,int_,mart_} sont interrogeables."
            )
    return sql
