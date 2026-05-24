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
LOYALTY_DIR = str(REPO_ROOT / "tests" / "fixtures" / "loyalty")
ORDERS_DIR = str(REPO_ROOT / "tests" / "fixtures" / "orders")


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
    """Load receipts + loyalty + orders fixtures into an isolated temporary DuckDB."""
    db = tmp_path / "carrefour.duckdb"
    load_all(
        source_dir=FIXTURES,
        loyalty_dir=LOYALTY_DIR,
        orders_dir=ORDERS_DIR,
        db_path=str(db),
        dataset="raw",
        pipelines_dir=tmp_path / "dlt",
    )
    return db


def test_load_all_loads_order_tables(loaded_all: Path):
    con = duckdb.connect(str(loaded_all))
    # dlt unnested the flattened order into child tables.
    # 2 order docs (root) -> 5 line items, 3 payment splits.
    assert con.execute("select count(*) from raw.orders").fetchone()[0] == 2
    assert con.execute("select count(*) from raw.orders__lines").fetchone()[0] == 5
    assert con.execute("select count(*) from raw.orders__payments").fetchone()[0] == 3
    # Price was pulled out of the nested offers[ean][offerId] dynamic keys.
    cols = {
        r[0]: r[1]
        for r in con.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='raw' and table_name='orders__lines'"
        ).fetchall()
    }
    assert cols["unit_price"] == "DOUBLE"
    assert cols["line_total"] == "DOUBLE"
    banane = con.execute(
        "select unit_price, line_total from raw.orders__lines where title = 'BANANE BIO'"
    ).fetchone()
    assert banane == (1.5, 3.0)


def test_orders_merge_is_idempotent(tmp_path):
    db = tmp_path / "carrefour.duckdb"
    pdir = tmp_path / "dlt"
    load_all(FIXTURES, LOYALTY_DIR, ORDERS_DIR, str(db), "raw", pipelines_dir=pdir)
    load_all(FIXTURES, LOYALTY_DIR, ORDERS_DIR, str(db), "raw", pipelines_dir=pdir)

    con = duckdb.connect(str(db))
    # merge on order_number => re-running never duplicates orders or their lines.
    assert con.execute("select count(*) from raw.orders").fetchone()[0] == 2
    assert con.execute("select count(distinct order_number) from raw.orders").fetchone()[0] == 2
    assert con.execute("select count(*) from raw.orders__lines").fetchone()[0] == 5


def test_load_all_loads_loyalty_tables(loaded_all: Path):
    con = duckdb.connect(str(loaded_all))
    # dlt unnested the monthly `history` array into a child table.
    # 3 month docs (root) -> 7 operations.
    assert con.execute("select count(*) from raw.loyalty").fetchone()[0] == 3
    assert con.execute("select count(*) from raw.loyalty__history").fetchone()[0] == 7
    # Amounts are typed as floats (incl. the "0,21" French-comma value, and burned which
    # is int on some rows -> coerced so dlt keeps one DOUBLE column, not a variant).
    cols = {
        r[0]: r[1]
        for r in con.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='raw' and table_name='loyalty__history'"
        ).fetchall()
    }
    assert cols["earned"] == "DOUBLE"
    assert cols["burned"] == "DOUBLE"
    # The comma-decimal "0,21" was coerced, not NULLed.
    earned = con.execute(
        "select earned from raw.loyalty__history where operation_id = '64070450001'"
    ).fetchone()[0]
    assert earned == 0.21


def test_loyalty_merge_is_idempotent(tmp_path):
    db = tmp_path / "carrefour.duckdb"
    pdir = tmp_path / "dlt"
    load_all(FIXTURES, LOYALTY_DIR, ORDERS_DIR, str(db), "raw", pipelines_dir=pdir)
    load_all(FIXTURES, LOYALTY_DIR, ORDERS_DIR, str(db), "raw", pipelines_dir=pdir)

    con = duckdb.connect(str(db))
    # loyalty merges on the month `_id` => re-running the same files never
    # duplicates months or their operations.
    assert con.execute("select count(*) from raw.loyalty").fetchone()[0] == 3
    assert con.execute("select count(distinct _id) from raw.loyalty").fetchone()[0] == 3
    assert con.execute("select count(*) from raw.loyalty__history").fetchone()[0] == 7


def _write_loyalty_month(directory: Path, month: str, store: str) -> None:
    """Write a minimal one-operation loyalty month doc (``_id`` + ``history``)."""
    import json

    directory.mkdir(parents=True, exist_ok=True)
    doc = {
        "_id": month,
        "history": [
            {
                "operationId": month,
                "date": f"{month[:4]}-{month[4:]}-15",
                "store": store,
                "earned": 0.10,
                "burned": 0.0,
                "canceled": False,
            }
        ],
    }
    (directory / f"loyalty_{month}.json").write_text(json.dumps(doc), encoding="utf-8")


def test_loyalty_merge_accumulates_across_months(tmp_path):
    """A fresh ~1-year extract must not erase prior history (the month-grain merge).

    Loads an older window, then a newer overlapping one, and asserts the table holds
    the union of months — proving DuckDB is the durable archive even though the live
    API only returns a rolling window. The overlapping month is replaced, not wiped.
    """
    from carrefour_receipts_api.elt.load import load_loyalty

    db = tmp_path / "carrefour.duckdb"
    pdir = tmp_path / "dlt"

    dir_a = tmp_path / "win_a"  # older window: 202301 + 202401(v1)
    _write_loyalty_month(dir_a, "202301", "STORE A")
    _write_loyalty_month(dir_a, "202401", "STORE V1")
    dir_b = tmp_path / "win_b"  # newer window: 202401(v2) + 202406
    _write_loyalty_month(dir_b, "202401", "STORE V2")
    _write_loyalty_month(dir_b, "202406", "STORE C")

    load_loyalty(str(dir_a), str(db), "raw", pipelines_dir=pdir)
    load_loyalty(str(dir_b), str(db), "raw", pipelines_dir=pdir)

    con = duckdb.connect(str(db))
    # months: union {202301, 202401, 202406}; the older 202301 survived the 2nd load.
    months = {r[0] for r in con.execute("select _id from raw.loyalty").fetchall()}
    assert months == {"202301", "202401", "202406"}
    # 202401 was replaced by the newer window's version (v2), not duplicated.
    stores = {r[0] for r in con.execute("select store from raw.loyalty__history").fetchall()}
    assert stores == {"STORE A", "STORE V2", "STORE C"}
    assert con.execute("select count(*) from raw.loyalty__history").fetchone()[0] == 3


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
