"""Natural-language financial assistant (Vanna 2.0 text-to-SQL) over the DuckDB marts.

The assistant answers questions in natural language by generating SQL, running it
**read-only** against the analytical layer (facts/dims/intermediate/marts — never the
raw PII tables), and optionally charting the result (Plotly). See ``docs/assistant.md``.
"""
