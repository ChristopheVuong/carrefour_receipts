"""Load raw Carrefour data (receipts + loyalty) into DuckDB with dlt.

Usage (CLI):
    python -m carrefour_receipts_api.elt.load \
        --source data/20250613 \
        --loyalty data/20250601-carrefour_loyalty.csv \
        --db carrefour.duckdb \
        --dataset raw

Two resources feed the ``raw`` dataset:
  - ``receipts``: one document per in-store receipt (JSON). Merged on the receipt
    ``id`` primary key, so re-loading the same files never creates duplicates.
    dlt unnests nested arrays into child tables
    (e.g. ``receipts__attributes__products__product``).
  - ``loyalty``: one row per loyalty line item (CSV). Merged on a *synthetic*
    row key (content signature + occurrence index) because a loyalty line has no
    natural key (``operationId`` repeats; ``_dlt_id`` is a per-load surrogate).
    The merge makes DuckDB the durable archive: since the live API only returns a
    rolling ~1-year window, replacing the table would silently drop older history;
    merging accumulates the union across loads instead (re-running never
    duplicates, and a fresh ~1-year extract never erases prior months).

The transformation (cleaning, the fidélité fuzzy-join, the star schema) then
happens in dbt (see ``transform/``).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import dlt

from carrefour_receipts_api import config
from carrefour_receipts_api.logging_config import get_logger

logger = get_logger(__name__)

# Loyalty CSV columns that hold numeric amounts (coerced from str -> float|None).
_LOYALTY_NUMERIC = ("earned", "burned", "itemRd")

# Business fields whose combination identifies a loyalty line (no natural key exists).
# The synthetic merge key is sha1(signature + occurrence index): two legitimately
# identical lines in the same operation get distinct keys via the occurrence counter.
_LOYALTY_KEY_FIELDS = (
    "operationId",
    "date",
    "itemLabel",
    "promotionLabel",
    "earned",
    "burned",
    "itemRd",
    "loyaltyOperation",
)


# --- Receipts ----------------------------------------------------------------
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
            logger.warning("skipping_malformed_json", file=str(file), error=str(exc))
            continue
        for record in doc if isinstance(doc, list) else [doc]:
            if record and isinstance(record, dict) and record.get("id"):
                count += 1
                yield record
            else:
                logger.warning("skipping_record_without_id", file=str(file))
    logger.info("receipts_yielded", count=count, source=str(source))


@dlt.resource(name="receipts", primary_key="id", write_disposition="merge")
def receipts_resource(source_dir: str | Path) -> Iterator[dict[str, Any]]:
    """dlt resource streaming receipt documents (merged on ``id``)."""
    yield from iter_receipt_files(source_dir)


# --- Loyalty -----------------------------------------------------------------
def _to_float(value: str | None) -> float | None:
    """Parse a loyalty amount; blank/invalid cells become ``None``."""
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _canon(value: Any) -> str:
    """Canonical string for a key field: stable across loads and float formats."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value).strip()


def _loyalty_signature(row: dict[str, Any]) -> str:
    """Content signature of a loyalty line (all business fields, canonicalised)."""
    return "|".join(_canon(row.get(field)) for field in _LOYALTY_KEY_FIELDS)


def iter_loyalty_rows(csv_path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield each loyalty line item from the CSV, with amounts coerced and a
    deterministic ``loyalty_row_key`` added for the dlt merge.

    The key is ``sha1(signature | occurrence)``: the signature dedups identical
    re-extracts across loads, and the occurrence index keeps legitimately
    duplicate lines (e.g. two identical items in one operation) distinct.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Loyalty CSV not found: {path}")

    count = 0
    seen: Counter[str] = Counter()
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            for field in _LOYALTY_NUMERIC:
                if field in row:
                    row[field] = _to_float(row[field])
            signature = _loyalty_signature(row)
            occurrence = seen[signature]
            seen[signature] += 1
            row["loyalty_row_key"] = hashlib.sha1(f"{signature}|{occurrence}".encode()).hexdigest()
            count += 1
            yield row
    logger.info("loyalty_yielded", count=count, source=str(path))


@dlt.resource(name="loyalty", primary_key="loyalty_row_key", write_disposition="merge")
def loyalty_resource(csv_path: str | Path) -> Iterator[dict[str, Any]]:
    """dlt resource streaming loyalty line items (merged on the synthetic key)."""
    yield from iter_loyalty_rows(csv_path)


# --- Pipeline ----------------------------------------------------------------
def _pipeline(db_path: str, dataset: str, pipelines_dir: str | Path | None):
    extra: dict[str, Any] = {}
    if pipelines_dir is not None:
        extra["pipelines_dir"] = str(pipelines_dir)
    return dlt.pipeline(
        pipeline_name="carrefour",
        destination=dlt.destinations.duckdb(db_path),
        dataset_name=dataset,
        **extra,
    )


def _row_counts(pipeline) -> dict[str, Any]:
    return {
        name: metrics
        for name, metrics in (pipeline.last_trace.last_normalize_info.row_counts or {}).items()
        if not name.startswith("_dlt")
    }


def load_receipts(
    source_dir: str | Path | None = None,
    db_path: str | None = None,
    dataset: str | None = None,
    pipelines_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the dlt pipeline loading receipts from ``source_dir`` into DuckDB.

    Defaults fall back to values from the environment / ``.env`` (see config).
    Returns a small summary dict (rows loaded) for logging/testing.
    """
    source_dir = source_dir if source_dir is not None else config.RECEIPTS_SOURCE_DIR
    db_path = db_path if db_path is not None else config.DUCKDB_PATH
    dataset = dataset if dataset is not None else config.DUCKDB_DATASET

    pipeline = _pipeline(db_path, dataset, pipelines_dir)
    info = pipeline.run(receipts_resource(source_dir))
    logger.info("receipts_load_complete", db_path=db_path, dataset=dataset)
    return {
        "db_path": db_path,
        "dataset": dataset,
        "row_counts": _row_counts(pipeline),
        "info": str(info),
    }


def load_loyalty(
    csv_path: str | Path | None = None,
    db_path: str | None = None,
    dataset: str | None = None,
    pipelines_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the dlt pipeline loading the loyalty CSV snapshot into DuckDB."""
    csv_path = csv_path if csv_path is not None else config.LOYALTY_SOURCE_CSV
    db_path = db_path if db_path is not None else config.DUCKDB_PATH
    dataset = dataset if dataset is not None else config.DUCKDB_DATASET

    pipeline = _pipeline(db_path, dataset, pipelines_dir)
    info = pipeline.run(loyalty_resource(csv_path))
    logger.info("loyalty_load_complete", db_path=db_path, dataset=dataset)
    return {
        "db_path": db_path,
        "dataset": dataset,
        "row_counts": _row_counts(pipeline),
        "info": str(info),
    }


def load_all(
    source_dir: str | Path | None = None,
    loyalty_csv: str | Path | None = None,
    db_path: str | None = None,
    dataset: str | None = None,
    pipelines_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Load both receipts and loyalty into the same ``raw`` dataset (one pipeline run)."""
    source_dir = source_dir if source_dir is not None else config.RECEIPTS_SOURCE_DIR
    loyalty_csv = loyalty_csv if loyalty_csv is not None else config.LOYALTY_SOURCE_CSV
    db_path = db_path if db_path is not None else config.DUCKDB_PATH
    dataset = dataset if dataset is not None else config.DUCKDB_DATASET

    pipeline = _pipeline(db_path, dataset, pipelines_dir)
    info = pipeline.run([receipts_resource(source_dir), loyalty_resource(loyalty_csv)])
    logger.info("full_load_complete", db_path=db_path, dataset=dataset)
    return {
        "db_path": db_path,
        "dataset": dataset,
        "row_counts": _row_counts(pipeline),
        "info": str(info),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load Carrefour data into DuckDB via dlt.")
    parser.add_argument(
        "--source",
        default=None,
        help="Directory of receipt JSON files (default: env RECEIPTS_SOURCE_DIR).",
    )
    parser.add_argument(
        "--loyalty",
        default=None,
        help="Loyalty CSV snapshot (default: env LOYALTY_SOURCE_CSV).",
    )
    parser.add_argument(
        "--no-loyalty", action="store_true", help="Load receipts only (skip loyalty)."
    )
    parser.add_argument(
        "--db", default=None, help="Path to the DuckDB database file (default: env DUCKDB_PATH)."
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Target DuckDB schema/dataset name (default: env DUCKDB_DATASET).",
    )
    parser.add_argument(
        "--pipelines-dir",
        default=None,
        help=(
            "Directory for dlt's pipeline state (default: dlt's own location). Set this to a "
            "persistent volume for containerized batch runs so state survives across runs."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.no_loyalty:
        summary = load_receipts(
            source_dir=args.source,
            db_path=args.db,
            dataset=args.dataset,
            pipelines_dir=args.pipelines_dir,
        )
    else:
        summary = load_all(
            source_dir=args.source,
            loyalty_csv=args.loyalty,
            db_path=args.db,
            dataset=args.dataset,
            pipelines_dir=args.pipelines_dir,
        )
    logger.info("row_counts", **summary["row_counts"])
