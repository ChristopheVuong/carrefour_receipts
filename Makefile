.PHONY: install lint format typecheck test elt dbt build clean

# Modern data stack dev workflow. Requires `uv` (https://docs.astral.sh/uv/).

install:  ## Create the venv and install dev + elt + analysis deps
	uv sync --extra elt --extra analysis

lint:  ## Ruff lint (modern stack + tests)
	uv run ruff check src/carrefour_receipts_api/config.py src/carrefour_receipts_api/elt tests

format:  ## Auto-format the modern stack code
	uv run ruff format src/carrefour_receipts_api/config.py src/carrefour_receipts_api/elt

typecheck:  ## Mypy on the modern stack code
	uv run mypy src/carrefour_receipts_api/config.py src/carrefour_receipts_api/elt

test:  ## Run offline tests (skip live-API integration tests)
	uv run pytest -m "not integration" -q

elt:  ## Load receipt JSON fixtures into DuckDB via dlt
	uv run python -m carrefour_receipts_api.elt.load

dbt:  ## Build + test the dbt models against DuckDB
	cd transform && uv run dbt build --profiles-dir .

build: elt dbt  ## Full data pipeline: load then transform

clean:  ## Remove the local DuckDB file and dbt artifacts
	rm -f carrefour.duckdb
	rm -rf transform/target transform/dbt_packages transform/logs
