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
        con.execute("select count(*) from raw.receipts__attributes__products__product").fetchone()[
            0
        ]
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


def test_loyalty_merge_is_idempotent(tmp_path):
    db = tmp_path / "carrefour.duckdb"
    pdir = tmp_path / "dlt"
    load_all(FIXTURES, LOYALTY_CSV, str(db), "raw", pipelines_dir=pdir)
    load_all(FIXTURES, LOYALTY_CSV, str(db), "raw", pipelines_dir=pdir)

    con = duckdb.connect(str(db))
    # loyalty merges on the synthetic loyalty_row_key => re-running the same CSV
    # never duplicates rows, and the key is unique.
    assert con.execute("select count(*) from raw.loyalty").fetchone()[0] == 8
    assert con.execute("select count(distinct loyalty_row_key) from raw.loyalty").fetchone()[0] == 8


def test_loyalty_merge_accumulates_overlapping_snapshots(tmp_path):
    """A fresh ~1-year extract must not erase prior history (the merge fix).

    Loads an older snapshot, then a newer one that overlaps it, and asserts the
    table holds the *union* with the overlap deduped — proving DuckDB is the
    durable archive even though the live API only returns a rolling window.
    """
    db = tmp_path / "carrefour.duckdb"
    pdir = tmp_path / "dlt"
    header = "operationId,date,earned,burned,itemLabel,promotionLabel,itemRd,loyaltyOperation\n"
    old_row = "111,2023-01-15,0.21,0.0,BANANE BIO,,0.10,Paiement en caisse\n"
    overlap_row = "222,2024-01-15,0.05,0.0,LAIT DEMI-ECREME 1L,,0.00,Paiement en caisse\n"
    new_row = "333,2024-06-20,0.30,0.0,POMME GALA,,0.15,Paiement en caisse\n"

    snapshot_a = tmp_path / "loyalty_a.csv"  # older window: old + overlap
    snapshot_a.write_text(header + old_row + overlap_row, encoding="utf-8")
    snapshot_b = tmp_path / "loyalty_b.csv"  # newer window: overlap + new
    snapshot_b.write_text(header + overlap_row + new_row, encoding="utf-8")

    from carrefour_receipts_api.elt.load import load_loyalty

    load_loyalty(str(snapshot_a), str(db), "raw", pipelines_dir=pdir)
    load_loyalty(str(snapshot_b), str(db), "raw", pipelines_dir=pdir)

    con = duckdb.connect(str(db))
    # union of {old, overlap, new} = 3 rows; the overlap appears once, the older
    # month survived the second load (no replace wipe).
    assert con.execute("select count(*) from raw.loyalty").fetchone()[0] == 3
    labels = {r[0] for r in con.execute("select item_label from raw.loyalty").fetchall()}
    assert labels == {"BANANE BIO", "LAIT DEMI-ECREME 1L", "POMME GALA"}


@pytest.mark.parametrize(
    "raw_value, expected",
    [("1.5", 1.5), ("0", 0.0), ("", None), ("   ", None), (None, None), ("n/a", None)],
)
def test_to_float_coerces_loyalty_amounts(raw_value, expected):
    assert _to_float(raw_value) == expected


def test_decimal_immediate_discount_is_not_truncated(tmp_path):
    """Regression: a per-line decimal discount mixed with integer 0s must survive.

    Without coercion, dlt infers BIGINT for immediate_discount (most lines are 0) and
    silently NULLs a real -1.1 — observed on a real receipt. The resource coerces the
    money fields to float so the column is DOUBLE and the discount is preserved.
    """
    import json

    receipt = {
        "id": "store_20260101_1-2-3",
        "attributes": {
            "dateKey": "20260101",
            "products": {
                "product": [
                    {
                        "label": "A",
                        "quantity": 1,
                        "unitPrice": 2.0,
                        "totalPrice": 2.0,
                        "immediateDiscount": 0,
                    },
                    {
                        "label": "B",
                        "quantity": 1,
                        "unitPrice": 2.19,
                        "totalPrice": 2.19,
                        "immediateDiscount": -1.1,
                    },
                ],
                "coupon": [],
            },
        },
    }
    src = tmp_path / "src"
    src.mkdir()
    (src / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")

    db = tmp_path / "carrefour.duckdb"
    load_receipts(str(src), str(db), "raw", pipelines_dir=tmp_path / "dlt")

    con = duckdb.connect(str(db))
    dtype = con.execute(
        "select data_type from information_schema.columns where table_schema='raw' "
        "and table_name='receipts__attributes__products__product' "
        "and column_name='immediate_discount'"
    ).fetchone()[0]
    assert dtype == "DOUBLE"
    discounts = {
        r[0]: r[1]
        for r in con.execute(
            "select label, immediate_discount from raw.receipts__attributes__products__product"
        ).fetchall()
    }
    assert discounts == {"A": 0.0, "B": -1.1}
