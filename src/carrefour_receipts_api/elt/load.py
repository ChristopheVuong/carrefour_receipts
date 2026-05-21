"""Load raw Carrefour receipt JSON into DuckDB with dlt.

Usage (CLI):
    python -m carrefour_receipts_api.elt.load \
        --source tests/fixtures/receipts \
        --db carrefour.duckdb \
        --dataset raw

The loader is idempotent: rows are merged on the receipt ``id`` primary key, so
loading the same files twice does not create duplicates. Nested arrays are
unnested by dlt into child tables (e.g. ``receipts__attributes__products__product``).
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import dlt

from carrefour_receipts_api import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def iter_receipt_files(source_dir: str | Path) -> Iterator[dict[str, Any]]:
    """Yield each receipt-detail JSON document found under ``source_dir``.

    Accepts both a single receipt object per file and a list of objects.
    """
    source = Path(source_dir)
    if not source.exists():
        raise FileNotFoundError(f"Source directory not found: {source}")

    count = 0
    for file in sorted(source.rglob("*.json")):
        try:
            doc = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed JSON %s: %s", file, exc)
            continue
        for record in doc if isinstance(doc, list) else [doc]:
            if record and isinstance(record, dict) and record.get("id"):
                count += 1
                yield record
            else:
                logger.warning("Skipping record without 'id' in %s", file)
    logger.info("Yielded %d receipt records from %s", count, source)


@dlt.resource(name="receipts", primary_key="id", write_disposition="merge")
def receipts_resource(source_dir: str | Path) -> Iterator[dict[str, Any]]:
    """dlt resource streaming receipt documents (merged on ``id``)."""
    yield from iter_receipt_files(source_dir)


def load_receipts(
    source_dir: str | Path | None = None,
    db_path: str | None = None,
    dataset: str | None = None,
    pipelines_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the dlt pipeline loading receipts from ``source_dir`` into DuckDB.

    Args:
        source_dir: directory of receipt JSON files.
        db_path: path to the target DuckDB file.
        dataset: target DuckDB schema name.
        pipelines_dir: optional dlt working/state directory (use a temp dir to
            keep test runs hermetic and independent of ``~/.dlt``).

    Returns a small summary dict (rows loaded) for logging/testing.

    Defaults fall back to values from the environment / ``.env`` (see config).
    """
    source_dir = source_dir if source_dir is not None else config.RECEIPTS_SOURCE_DIR
    db_path = db_path if db_path is not None else config.DUCKDB_PATH
    dataset = dataset if dataset is not None else config.DUCKDB_DATASET

    extra: dict[str, Any] = {}
    if pipelines_dir is not None:
        extra["pipelines_dir"] = str(pipelines_dir)
    pipeline = dlt.pipeline(
        pipeline_name="carrefour",
        destination=dlt.destinations.duckdb(db_path),
        dataset_name=dataset,
        **extra,
    )
    info = pipeline.run(receipts_resource(source_dir))
    logger.info("Load complete -> %s (dataset=%s)", db_path, dataset)
    row_counts = {
        name: metrics
        for name, metrics in (pipeline.last_trace.last_normalize_info.row_counts or {}).items()
        if not name.startswith("_dlt")
    }
    return {"db_path": db_path, "dataset": dataset, "row_counts": row_counts, "info": str(info)}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load Carrefour receipt JSON into DuckDB via dlt.")
    parser.add_argument(
        "--source",
        default=None,
        help="Directory of receipt JSON files (default: env RECEIPTS_SOURCE_DIR).",
    )
    parser.add_argument(
        "--db", default=None, help="Path to the DuckDB database file (default: env DUCKDB_PATH)."
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Target DuckDB schema/dataset name (default: env DUCKDB_DATASET).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary = load_receipts(source_dir=args.source, db_path=args.db, dataset=args.dataset)
    logger.info("Row counts: %s", summary["row_counts"])
