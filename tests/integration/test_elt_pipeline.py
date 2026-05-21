"""Offline tests for the dlt -> DuckDB extract-load layer.

These exercise the real dlt pipeline against committed JSON fixtures (no network,
no live API), so they run in CI. They cover:
  - automatic unnesting of the receipt document into child tables;
  - idempotency of the ``merge`` load (re-running never duplicates rows).
"""

from pathlib import Path

import duckdb
import pytest

from carrefour_receipts_api.elt.load import _to_float, load_all, load_receipts

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = str(REPO_ROOT / "tests" / "fixtures" / "receipts")
LOYALTY_CSV = str(REPO_ROOT / "tests" / "fixtures" / "loyalty" / "loyalty.csv")


@pytest.fixture
def loaded_db(tmp_path) -> Path:
    """Load fixtures into an isolated temporary DuckDB + dlt state dir."""
    db = tmp_path / "carrefour.duckdb"
    load_receipts(
        source_dir=FIXTURES,
        db_path=str(db),
        dataset="raw",
        pipelines_dir=tmp_path / "dlt",
    )
    return db


def test_loads_header_and_child_tables(loaded_db: Path):
    con = duckdb.connect(str(loaded_db))
    tables = {
        r[0]
        for r in con.execute(
            "select table_name from information_schema.tables where table_schema = 'raw'"
        ).fetchall()
    }
    # dlt unnested the nested arrays into dedicated child tables.
    assert "receipts" in tables
    assert "receipts__attributes__products__product" in tables
    assert "receipts__attributes__vats" in tables
    assert "receipts__attributes__payment_info" in tables

    assert con.execute("select count(*) from raw.receipts").fetchone()[0] == 3
    assert (
        con.execute(
            "select count(*) from raw.receipts__attributes__products__product"
        ).fetchone()[0]
        == 12
    )


def test_merge_load_is_idempotent(tmp_path):
    db = tmp_path / "carrefour.duckdb"
    pdir = tmp_path / "dlt"
    load_receipts(FIXTURES, str(db), "raw", pipelines_dir=pdir)
    load_receipts(FIXTURES, str(db), "raw", pipelines_dir=pdir)

    con = duckdb.connect(str(db))
    # merge on primary key `id` => re-running does not create duplicates.
    assert con.execute("select count(*) from raw.receipts").fetchone()[0] == 3
    assert con.execute("select count(distinct id) from raw.receipts").fetchone()[0] == 3


@pytest.fixture
def loaded_all(tmp_path) -> Path:
    """Load receipts + loyalty fixtures into an isolated temporary DuckDB."""
    db = tmp_path / "carrefour.duckdb"
    load_all(
        source_dir=FIXTURES,
        loyalty_csv=LOYALTY_CSV,
        db_path=str(db),
        dataset="raw",
        pipelines_dir=tmp_path / "dlt",
    )
    return db


def test_load_all_loads_loyalty_table(loaded_all: Path):
    con = duckdb.connect(str(loaded_all))
    assert con.execute("select count(*) from raw.loyalty").fetchone()[0] == 8
    # Numeric loyalty amounts are typed as floats, not strings.
    cols = {
        r[0]: r[1]
        for r in con.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='raw' and table_name='loyalty'"
        ).fetchall()
    }
    assert cols["earned"] == "DOUBLE"
    assert cols["item_rd"] == "DOUBLE"


def test_loyalty_replace_is_idempotent(tmp_path):
    db = tmp_path / "carrefour.duckdb"
    pdir = tmp_path / "dlt"
    load_all(FIXTURES, LOYALTY_CSV, str(db), "raw", pipelines_dir=pdir)
    load_all(FIXTURES, LOYALTY_CSV, str(db), "raw", pipelines_dir=pdir)

    con = duckdb.connect(str(db))
    # loyalty uses write_disposition="replace" => re-running keeps a single snapshot.
    assert con.execute("select count(*) from raw.loyalty").fetchone()[0] == 8


@pytest.mark.parametrize(
    "raw_value, expected",
    [("1.5", 1.5), ("0", 0.0), ("", None), ("   ", None), (None, None), ("n/a", None)],
)
def test_to_float_coerces_loyalty_amounts(raw_value, expected):
    assert _to_float(raw_value) == expected
