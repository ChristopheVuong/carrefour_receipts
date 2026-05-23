# Deployment — batch ingestion

The default deployment is a single read-only dashboard container over a host-built DuckDB
(see [dashboard.md](dashboard.md)). This page covers the **optional** containerized batch:
running the `make build` step (dlt extract-load + dbt) as a re-runnable ingestion job, so it
can be deployed/scheduled instead of run by hand.

## What is and isn't containerized

| Stage | Where | Why |
| --- | --- | --- |
| Auth (login → cookies) | **host CLI** | needs a real browser (patchright `headless=False`, Cloudflare) |
| Extraction (fetch → files) | **host CLI** | depends on the fresh cookies; pairs with auth |
| **EL (dlt) + dbt build** | **`builder` container** | pure compute over files → DuckDB; no browser |
| Dashboard | dashboard container | read-only viewer over the marts |

The builder **does not extract** from Carrefour — it only transforms files already extracted
on the host (mounted read-only).

## Why the batch is safe to re-run

The load is **merge-based** (receipts on `id`, loyalty on a synthetic key — see
[processing.md](processing.md)), so re-running is idempotent and accumulates history rather than
replacing it. The only extra requirement for a container is **state persistence**: keep both
`carrefour.duckdb` and dlt's pipeline state on a durable volume (the `--pipelines-dir` flag
points dlt's state there).

## Running the batch

```bash
# 0. (host) extract fresh data — needs a browser; see usage.md
make auth-service
uv run python -m carrefour_receipts_api.user_api_extractor

# 1. build the marts in a container (dlt load + dbt build) into the shared volume
docker compose -f docker-compose.batch.yml run --rm builder

# 2. serve them
docker compose -f docker-compose.batch.yml up dashboard
```

`builder` is a **one-shot** job (use `run`, not `up`): it loads, builds, then exits with the
pipeline's status code.

### Volumes & paths

The named volume `carrefour_state` holds **both** `carrefour.duckdb` and the dlt state
(`.dlt/`). `DUCKDB_PATH` is read by both the EL (`config.DUCKDB_PATH`) and the dbt profile
(`{{ env_var('DUCKDB_PATH') }}` in [transform/profiles.yml](../transform/profiles.yml)), so the
DB path has a single source of truth. Set `LOYALTY_SOURCE_CSV` in
[docker-compose.batch.yml](../docker-compose.batch.yml) to your actual loyalty CSV filename.

A named volume (not a single-file bind mount) is used on purpose: bind-mounting a not-yet-existing
`carrefour.duckdb` would make Docker create a *directory* by that name and break the build.

## Scheduling

Triggering is left to you (no orchestrator is bundled). Any scheduler that can run a command
works — e.g. a host cron entry:

```cron
# 03:00 daily: refresh marts from whatever the host has extracted
0 3 * * * cd /path/to/carrefour_receipts && docker compose -f docker-compose.batch.yml run --rm builder >> /var/log/carrefour-batch.log 2>&1
```

Note the cron only rebuilds marts from already-extracted files; refreshing the *source* data
still needs the host extraction step (browser).
