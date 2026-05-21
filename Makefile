.PHONY: install install-ml lint format typecheck test elt dbt build clean

# Modern data stack dev workflow. Requires `uv` (https://docs.astral.sh/uv/).

# Files that make up the modern data stack (kept in sync with CI lint scope).
STACK := src/carrefour_receipts_api/config.py src/carrefour_receipts_api/embeddings.py src/carrefour_receipts_api/matching.py src/carrefour_receipts_api/elt

install:  ## Create the venv and install dev + elt + analysis deps
	uv sync --extra elt --extra analysis

install-ml:  ## Also install the semantic-matching extra (fastembed, ONNX — no torch)
	uv sync --extra elt --extra analysis --extra ml

lint:  ## Ruff lint (modern stack + tests)
	uv run ruff check $(STACK) tests

format:  ## Auto-format the modern stack code
	uv run ruff format $(STACK)

typecheck:  ## Mypy on the modern stack code
	uv run mypy $(STACK)

test:  ## Run offline tests (skip live-API integration tests)
	uv run pytest -m "not integration" -q

elt:  ## Load receipt + loyalty fixtures into DuckDB via dlt
	uv run python -m carrefour_receipts_api.elt.load

dbt:  ## Build + test the dbt models against DuckDB
	cd transform && uv run dbt build --profiles-dir .

build: elt dbt  ## Full data pipeline: load then transform

clean:  ## Remove the local DuckDB file and dbt artifacts
	rm -f carrefour.duckdb carrefour.duckdb.wal
	rm -rf transform/target transform/dbt_packages transform/logs
