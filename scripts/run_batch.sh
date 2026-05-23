#!/usr/bin/env bash
# One-shot batch ingestion: dlt extract-load then dbt build (= `make build`), wired to
# read/write a persistent volume. Used as the entrypoint of the builder image
# (Dockerfile.builder). Exits non-zero if either stage fails, so a scheduler sees it.
#
# Paths come from the environment (set by docker-compose.batch.yml):
#   DUCKDB_PATH         DuckDB file on the volume (read by both dlt and the dbt profile)
#   DUCKDB_DATASET      target dlt schema (default raw)
#   RECEIPTS_SOURCE_DIR directory of extracted receipt JSON (recursive)
#   LOYALTY_SOURCE_CSV  loyalty CSV
#   DLT_PIPELINES_DIR   dlt pipeline state dir on the volume (survives across runs)
set -euo pipefail

uv run --no-dev --extra elt --extra analysis python -m carrefour_receipts_api.elt.load \
  --source "${RECEIPTS_SOURCE_DIR}" \
  --loyalty "${LOYALTY_SOURCE_CSV}" \
  --dataset "${DUCKDB_DATASET:-raw}" \
  --pipelines-dir "${DLT_PIPELINES_DIR}"

cd transform
uv run --no-dev --extra elt --extra analysis dbt build --profiles-dir .
