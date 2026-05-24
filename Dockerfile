# Streamlit analytics dashboard over the DuckDB marts.
# Build:  docker build -t carrefour-dashboard .
# Run:    docker run --rm -p 8501:8501 -v "$PWD/carrefour.duckdb:/data/carrefour.duckdb" carrefour-dashboard
#
# The image ships only the dashboard surface (no scraping/ml). It expects a
# pre-built DuckDB file (run `make build` on the host) mounted at /data.
FROM python:3.13-slim

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DUCKDB_PATH=/data/carrefour.duckdb

# Install dependencies first (better layer caching), then the package.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --no-dev --extra dashboard --frozen

EXPOSE 8501

# Streamlit needs to bind to all interfaces inside the container.
CMD ["uv", "run", "--no-dev", "--extra", "dashboard", \
     "streamlit", "run", "src/carrefour_receipts_api/dashboard/dashboard.py", \
     "--server.address=0.0.0.0", "--server.port=8501"]
