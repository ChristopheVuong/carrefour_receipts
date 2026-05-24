"""Pre-flight checks for the NL financial assistant.

Verifies DuckDB connectivity, analytical-layer tables, dbt manifest (grounding),
and Vanna 2.0 agent imports — before you waste time launching Streamlit.

Usage:
    uv run --extra assistant tools/check_assistant.py
"""

from __future__ import annotations

import sys

import duckdb

from carrefour_receipts_api import config
from carrefour_receipts_api.assistant.sql_guard import ALLOWED_TABLE_PREFIXES

PASS = "[OK]"
FAIL = "[FAIL]"


def _check(label: str, fn) -> bool:
    try:
        result = fn()
        print(f"{PASS} {label}" + (f": {result}" if result else ""))
        return True
    except Exception as exc:
        print(f"{FAIL} {label}: {exc}", file=sys.stderr)
        return False


def check_duckdb() -> str:
    con = duckdb.connect(config.DUCKDB_PATH, read_only=True)
    try:
        rows = con.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'main' order by table_name"
        ).fetchall()
        tables = [r[0] for r in rows]
        analytical = [t for t in tables if t.startswith(ALLOWED_TABLE_PREFIXES)]
        if not analytical:
            raise RuntimeError(
                f"no analytical tables found in {config.DUCKDB_PATH!r} — run `make build` first"
            )
        return f"{len(analytical)} analytical tables ({', '.join(analytical[:4])}{'…' if len(analytical) > 4 else ''})"
    finally:
        con.close()


def check_schema_card() -> str:
    from carrefour_receipts_api.assistant.grounding import schema_card
    card = schema_card()
    lines = card.splitlines()
    table_count = sum(1 for l in lines if l.startswith("### main."))
    return f"schema card built — {table_count} tables, {len(card)} chars"


def check_vanna_imports() -> str:
    from vanna import Agent, AgentConfig, ToolRegistry  # noqa: F401
    from vanna.integrations.openai import OpenAILlmService  # noqa: F401
    from vanna.integrations.duckdb import DuckDBRunner  # noqa: F401
    from vanna.tools import RunSqlTool, VisualizeDataTool  # noqa: F401
    import vanna
    return f"vanna {vanna.__version__} — all required symbols importable"


def check_llm_config() -> str:
    if not config.ASSISTANT_LLM_API_KEY:
        raise RuntimeError("ASSISTANT_LLM_API_KEY not set — check .env (run tools/check_llm.py to test the endpoint)")
    return f"model={config.ASSISTANT_MODEL!r} base_url={config.ASSISTANT_LLM_BASE_URL!r}"


def main() -> None:
    print(f"DuckDB path : {config.DUCKDB_PATH}\n")
    results = [
        _check("DuckDB connection + analytical tables", check_duckdb),
        _check("Schema card (grounding)", check_schema_card),
        _check("Vanna 2.0 imports", check_vanna_imports),
        _check("LLM config", check_llm_config),
    ]
    print()
    if all(results):
        print("All checks passed — run the assistant with:  make assistant")
    else:
        print("Fix the errors above before launching.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
