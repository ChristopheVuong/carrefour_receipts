"""Offline query tests for the modern stack (DuckDB).

A monthly summary (count + total paid, grouped by year-month) expressed as plain
SQL over the dlt-loaded ``raw.receipts`` table — no network — so it runs in CI.
This mirrors the summary that ``fct_receipts`` exposes in the dbt layer.
"""

from pathlib import Path

import duckdb
import pytest

from carrefour_receipts_api.elt.load import load_receipts

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = str(REPO_ROOT / "tests" / "fixtures" / "receipts")


@pytest.fixture
def con(tmp_path) -> duckdb.DuckDBPyConnection:
    db = tmp_path / "carrefour.duckdb"
    load_receipts(FIXTURES, str(db), "raw", pipelines_dir=tmp_path / "dlt")
    return duckdb.connect(str(db), read_only=True)


def test_monthly_summary_aggregation(con: duckdb.DuckDBPyConnection):
    """Group receipts by year-month and total the paid amount (SQL == ex-Mongo)."""
    rows = con.execute(
        """
        select
            strftime(strptime(attributes__date_key, '%Y%m%d'), '%Y-%m') as year_month,
            count(*)                                as receipt_count,
            round(sum(attributes__total_paid_amount), 2) as total_paid
        from raw.receipts
        group by 1
        order by 1
        """
    ).fetchall()

    assert [r[0] for r in rows] == ["2024-01", "2024-02", "2024-03"]
    assert [r[1] for r in rows] == [1, 1, 1]
    assert [r[2] for r in rows] == [12.40, 23.07, 8.31]


def test_total_paid_across_all_receipts(con: duckdb.DuckDBPyConnection):
    total = con.execute(
        "select round(sum(attributes__total_paid_amount), 2) from raw.receipts"
    ).fetchone()[0]
    assert total == pytest.approx(43.78)
