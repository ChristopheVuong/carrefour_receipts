# Batch ingestion pipeline: dlt extract-load + dbt build (the `make build` step).
# Build:  docker build -f Dockerfile.builder -t carrefour-builder .
# Run:    docker compose -f docker-compose.batch.yml run --rm builder
#
# Unlike the dashboard image, this one carries the dbt project (transform/) and the
# elt+analysis extras (dbt-duckdb, dlt, rapidfuzz/scipy/sklearn for the Python dbt
# models). It writes the DuckDB file + dlt state to a mounted volume and exits — it
# does NOT extract from Carrefour (no browser); it only transforms files already
# extracted on the host.
FROM python:3.13-slim

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies first (better layer caching), then the package + dbt project.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY transform ./transform
RUN uv sync --no-dev --extra elt --extra analysis --frozen

COPY scripts/run_batch.sh /usr/local/bin/run_batch.sh
RUN chmod +x /usr/local/bin/run_batch.sh

# One-shot batch: load (dlt) then build (dbt), then exit with the pipeline's status.
ENTRYPOINT ["/usr/local/bin/run_batch.sh"]
