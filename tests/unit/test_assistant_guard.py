"""Unit tests for the assistant read-only SQL guardrail (sqlglot only, no LLM/db)."""

import pytest

pytest.importorskip("sqlglot")  # skipped when the `assistant` extra isn't installed

from carrefour_receipts_api.assistant.sql_guard import (  # noqa: E402
    UnsafeSqlError,
    validate_read_only_sql,
)

pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    "sql",
    [
        "select * from main.mart_monthly_spend",
        "SELECT category, sum(spend) FROM main.mart_category_insights GROUP BY 1",
        "select * from fct_receipt_lines limit 10",  # unqualified -> defaults to main
        "with t as (select * from main.int_purchases) select channel, sum(total_paid) from t group by 1",
        "select * from main.fct_orders union all select * from main.fct_receipts",
        "select * from main.dim_date",
    ],
)
def test_accepts_read_only_analytical_queries(sql):
    assert validate_read_only_sql(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "insert into main.fct_receipts values (1)",
        "update main.fct_receipts set total_paid = 0",
        "delete from main.fct_receipts",
        "drop table main.fct_receipts",
        "create table main.x as select 1",
        "attach 'evil.db' as e",
        "pragma database_list",
        "copy main.fct_receipts to 'out.csv'",
    ],
)
def test_rejects_writes_ddl_and_commands(sql):
    with pytest.raises(UnsafeSqlError):
        validate_read_only_sql(sql)


def test_rejects_multiple_statements():
    with pytest.raises(UnsafeSqlError):
        validate_read_only_sql("select 1 from main.fct_receipts; select 2 from main.fct_orders")


@pytest.mark.parametrize(
    "sql",
    [
        "select * from raw.receipts",  # raw schema (PII) blocked
        "select * from main.stg_receipts",  # stg exposes loyalty_card_number
        "select * from stg_receipts",
        "select * from main.seed_product_categories",  # not in fct_/dim_/int_/mart_
    ],
)
def test_rejects_tables_outside_allowlist(sql):
    with pytest.raises(UnsafeSqlError):
        validate_read_only_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "select * from read_csv('/etc/passwd')",
        "select * from read_parquet('s3://x/y.parquet')",
        "select * from glob('/**')",
    ],
)
def test_rejects_file_reading_functions(sql):
    with pytest.raises(UnsafeSqlError):
        validate_read_only_sql(sql)
