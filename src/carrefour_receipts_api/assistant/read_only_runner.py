"""Read-only DuckDB runner for the Vanna assistant.

Subclasses Vanna's ``DuckDBRunner`` to (1) open the database **read-only** and (2) pass
every generated query through :func:`validate_read_only_sql` before execution — so the
assistant can only run safe SELECTs over the analytical layer. Executed ``(sql, df)``
pairs are recorded so the Streamlit page can show the SQL and the result table.
"""

from __future__ import annotations

import pandas as pd
from vanna.capabilities.sql_runner import RunSqlToolArgs
from vanna.core.tool import ToolContext
from vanna.integrations.duckdb import DuckDBRunner

from carrefour_receipts_api import config
from carrefour_receipts_api.assistant.sql_guard import validate_read_only_sql

# Hard cap on rows returned to the LLM / UI (keeps prompts and charts bounded).
MAX_ROWS = 5000


class ReadOnlyDuckDBRunner(DuckDBRunner):
    """DuckDB runner that enforces a read-only connection + the SQL guardrail."""

    def __init__(self, database_path: str | None = None) -> None:
        # read_only=True flows through DuckDBRunner(**kwargs) into duckdb.connect().
        super().__init__(database_path=database_path or config.DUCKDB_PATH, read_only=True)
        # (sql, dataframe) executed during the current turn — read by the UI, then cleared.
        self.executed: list[tuple[str, pd.DataFrame]] = []

    async def run_sql(self, args: RunSqlToolArgs, context: ToolContext) -> pd.DataFrame:
        validate_read_only_sql(args.sql)  # raises UnsafeSqlError if not a safe read
        df = await super().run_sql(args, context)
        if len(df) > MAX_ROWS:
            df = df.head(MAX_ROWS)
        self.executed.append((args.sql, df))
        return df
