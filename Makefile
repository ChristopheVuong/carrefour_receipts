.PHONY: install install-ml lint format format-check typecheck test elt dbt build clean dashboard docs-dbt docker-build docker-run auth-service

# Modern data stack dev workflow. Requires `uv` (https://docs.astral.sh/uv/).

# Files that make up the modern data stack (kept in sync with CI lint scope).
STACK := src/carrefour_receipts_api/config.py src/carrefour_receipts_api/embeddings.py src/carrefour_receipts_api/matching.py src/carrefour_receipts_api/categorization.py src/carrefour_receipts_api/logging_config.py src/carrefour_receipts_api/elt src/carrefour_receipts_api/dashboard src/carrefour_receipts_api/auth_service

install:  ## Create the venv and install the full local stack (dev + `all` extra)
	uv sync --extra all

install-ml:  ## Full stack plus the semantic-matching extra (fastembed, ONNX — no torch)
	uv sync --extra all --extra ml

lint:  ## Ruff lint (modern stack + tests)
	uv run ruff check $(STACK) tests

format:  ## Auto-format the modern stack code
	uv run ruff format $(STACK)

format-check:  ## Check formatting without modifying files (CI / pre-commit parity)
	uv run ruff format --check $(STACK)

typecheck:  ## Mypy on the modern stack code
	uv run mypy $(STACK)

test:  ## Run offline tests with coverage (skip live-API integration tests)
	uv run pytest -m "not integration" --cov=carrefour_receipts_api --cov-report=term-missing -q

elt:  ## Load receipt + loyalty fixtures into DuckDB via dlt
	uv run python -m carrefour_receipts_api.elt.load

dbt:  ## Build + test the dbt models against DuckDB
	cd transform && uv run dbt build --profiles-dir .

build: elt dbt  ## Full data pipeline: load then transform

docs-dbt:  ## Generate + serve the dbt documentation site (independent of the README)
	cd transform && uv run dbt docs generate --profiles-dir . && uv run dbt docs serve --profiles-dir .

dashboard:  ## Run the Streamlit analytics dashboard (needs `make build` first)
	uv run --extra dashboard streamlit run src/carrefour_receipts_api/dashboard/app.py

auth-service:  ## Run the FastAPI auth service (browser login -> cookies) at :8000
	uv run --extra api --extra scraping uvicorn carrefour_receipts_api.auth_service.app:app --port 8000

docker-build:  ## Build the dashboard Docker image
	docker build -t carrefour-dashboard .

docker-run:  ## Run the dashboard container against the local carrefour.duckdb
	docker run --rm -p 8501:8501 -v "$(PWD)/carrefour.duckdb:/data/carrefour.duckdb:ro" carrefour-dashboard

clean:  ## Remove the local DuckDB file and dbt artifacts
	rm -f carrefour.duckdb carrefour.duckdb.wal
	rm -rf transform/target transform/dbt_packages transform/logs
