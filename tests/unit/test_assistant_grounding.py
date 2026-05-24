"""Unit tests for the assistant grounding schema card (DuckDB + fake manifest, no LLM)."""

import json
from pathlib import Path

import pytest

pytest.importorskip("duckdb")  # CI has duckdb via the elt extra
pytest.importorskip("sqlglot")  # schema_card imports sql_guard (sqlglot)

import duckdb  # noqa: E402

from carrefour_receipts_api.assistant.grounding import EXAMPLE_QUERIES, schema_card  # noqa: E402

pytestmark = pytest.mark.fast


def _make_db(path: Path) -> None:
    con = duckdb.connect(str(path))
    con.execute("create schema if not exists main")
    con.execute("create table main.fct_receipts(receipt_id varchar, total_paid double)")
    con.execute("create table main.mart_monthly_spend(year_month varchar, total_paid double)")
    con.execute("create table main.stg_receipts(loyalty_card_number varchar)")  # must be excluded
    con.close()


def _make_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "nodes": {
            "model.carrefour.fct_receipts": {
                "resource_type": "model",
                "schema": "main",
                "name": "fct_receipts",
                "description": "One row per receipt.",
                "columns": {"total_paid": {"description": "Net amount paid."}},
            }
        }
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_schema_card_includes_allowlisted_tables_and_descriptions(tmp_path):
    db = tmp_path / "t.duckdb"
    manifest = tmp_path / "target" / "manifest.json"
    _make_db(db)
    _make_manifest(manifest)

    card = schema_card(db_path=str(db), manifest_path=manifest)

    assert "main.fct_receipts" in card
    assert "main.mart_monthly_spend" in card
    assert "One row per receipt." in card  # model description from manifest
    assert "Net amount paid." in card  # column description from manifest
    assert "total_paid (DOUBLE)" in card or "total_paid (DOUBLE PRECISION)".lower() in card.lower()


def test_schema_card_excludes_stg_and_raw(tmp_path):
    db = tmp_path / "t.duckdb"
    _make_db(db)
    card = schema_card(db_path=str(db), manifest_path=tmp_path / "missing.json")
    assert "stg_receipts" not in card  # PII (loyalty card number) never exposed
    assert "loyalty_card_number" not in card


def test_schema_card_contains_curated_examples(tmp_path):
    db = tmp_path / "t.duckdb"
    _make_db(db)
    card = schema_card(db_path=str(db), manifest_path=tmp_path / "missing.json")
    assert "SQL:" in card
    assert any(q in card for q, _ in EXAMPLE_QUERIES)
