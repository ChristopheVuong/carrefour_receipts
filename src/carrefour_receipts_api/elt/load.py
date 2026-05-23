"""Load raw Carrefour data (receipts + loyalty) into DuckDB with dlt.

Usage (CLI):
    python -m carrefour_receipts_api.elt.load \
        --source data \
        --loyalty data \
        --db carrefour.duckdb \
        --dataset raw

Two resources feed the ``raw`` dataset, both from JSON:
  - ``receipts``: one document per in-store receipt. Merged on the receipt
    ``id`` primary key, so re-loading the same files never creates duplicates.
    dlt unnests nested arrays into child tables
    (e.g. ``receipts__attributes__products__product``).
  - ``loyalty``: one document per month (``_id`` = ``YYYYMM``) carrying a
    ``history`` array of line items. dlt unnests ``history`` into the child table
    ``loyalty__history``. Merged on the month ``_id``: re-loading a month replaces
    its lines while older months (absent from a fresh ~1-year extract) are kept,
    so DuckDB stays the durable archive of the rolling window. The per-line key is
    computed downstream in dbt (``stg_loyalty``), not here.
  - ``orders``: one document per Drive order (merged on ``order_number``). The raw
    JSON buries line prices behind dynamic dict keys (``offers[ean][offerId]``),
    which dlt can't unnest, so each order is flattened in Python first into
    ``{header..., payments[], lines[]}``; dlt then unnests ``lines`` into
    ``orders__lines`` and ``payments`` into ``orders__payments``.

The transformation (cleaning, the fidélité fuzzy-join, the star schema) then
happens in dbt (see ``transform/``).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import dlt

from carrefour_receipts_api import config
from carrefour_receipts_api.logging_config import get_logger

logger = get_logger(__name__)

# Loyalty history fields that hold numeric amounts (coerced to float|None so dlt
# types them DOUBLE and the French decimal comma "0,21" doesn't become NULL).
_LOYALTY_NUMERIC = ("earned", "burned", "itemRd")


# --- Receipts ----------------------------------------------------------------
# Product money fields that must stay decimal. dlt infers a column's type from the values
# it sees: immediateDiscount is usually 0 (int), so dlt picks BIGINT and then silently
# NULLs a genuine decimal like -1.1. Coercing to float forces a DOUBLE column.
_RECEIPT_PRODUCT_FLOAT_FIELDS = ("immediateDiscount", "unitPrice", "totalPrice")


def _coerce_receipt_numbers(record: dict[str, Any]) -> None:
    """In place: force decimal-capable product fields to float so dlt types them DOUBLE."""
    attributes = record.get("attributes")
    if not isinstance(attributes, dict):
        return
    products = attributes.get("products")
    items = products.get("product") if isinstance(products, dict) else None
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        for field in _RECEIPT_PRODUCT_FLOAT_FIELDS:
            value = item.get(field)
            if value is not None:
                try:
                    item[field] = float(value)
                except (TypeError, ValueError):
                    pass


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
                _coerce_receipt_numbers(record)
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
    """Parse a loyalty amount; blank/invalid cells become ``None``.

    Accepts the French decimal comma ("0,21" -> 0.21): these amounts are cents with
    no thousands separator, so a lone comma is the decimal point. Without this, a
    comma value would become ``None`` and silently corrupt the loyalty merge key.
    """
    if value is None or value.strip() == "":
        return None
    text = value.strip()
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_loyalty_numbers(doc: dict[str, Any]) -> None:
    """In place: coerce each history line's amount fields to float (handles "0,21")."""
    history = doc.get("history")
    if not isinstance(history, list):
        return
    for item in history:
        if not isinstance(item, dict):
            continue
        for field in _LOYALTY_NUMERIC:
            if field in item:
                item[field] = (
                    _to_float(item[field]) if isinstance(item[field], str) else item[field]
                )


def iter_loyalty_files(source_dir: str | Path) -> Iterator[dict[str, Any]]:
    """Yield each monthly loyalty document (one ``history`` array per month) under
    ``source_dir``.

    Selects JSON docs carrying a ``history`` list (receipt details have ``id`` and
    scroll pages have neither, so both are ignored). When several extraction runs
    produced the same month (same ``_id``), only the most recent file is kept (files
    are timestamp-prefixed, so the last in sorted order wins) for a deterministic
    month-grain merge.
    """
    source = Path(source_dir)
    if not source.exists():
        raise FileNotFoundError(f"Loyalty source directory not found: {source}")

    by_month: dict[str, dict[str, Any]] = {}
    for file in sorted(source.rglob("*.json")):
        try:
            doc = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("skipping_malformed_json", file=str(file), error=str(exc))
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("history"), list):
            continue
        month = doc.get("_id")
        if not month:
            logger.warning("skipping_loyalty_doc_without_id", file=str(file))
            continue
        _coerce_loyalty_numbers(doc)
        by_month[str(month)] = doc  # later (more recent) file wins

    count = 0
    for doc in by_month.values():
        count += 1
        yield doc
    logger.info("loyalty_yielded", months=count, source=str(source))


@dlt.resource(name="loyalty", primary_key="_id", write_disposition="merge")
def loyalty_resource(source_dir: str | Path) -> Iterator[dict[str, Any]]:
    """dlt resource streaming monthly loyalty docs (merged on the month ``_id``)."""
    yield from iter_loyalty_files(source_dir)


# --- Orders (Drive) ----------------------------------------------------------
# Drive order detail JSON nests the line price behind *dynamic* dict keys
# (offers[ean][offerId].attributes.price), which dlt cannot unnest into clean tables.
# So we flatten in Python here: each order becomes {header..., payments[], lines[]} with
# the price pulled out, and dlt then unnests the clean `lines`/`payments` arrays.
def _as_float(value: Any) -> float | None:
    """Coerce a numeric/str amount to float (forces dlt DOUBLE; handles "0,21")."""
    if value is None:
        return None
    if isinstance(value, str):
        return _to_float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_offer_price(product_attrs: dict[str, Any]) -> dict[str, Any]:
    """Return the price dict from a product's first offer, or ``{}`` if absent.

    Lines bury the price under dynamic keys ``offers[ean][offerId].attributes.price``;
    there is one offer per line in practice, so take the first at each level.
    """
    offers = product_attrs.get("offers")
    if not isinstance(offers, dict):
        return {}
    by_offer = next((v for v in offers.values() if isinstance(v, dict)), None)
    if not by_offer:
        return {}
    offer = next((v for v in by_offer.values() if isinstance(v, dict)), None)
    if not offer:
        return {}
    price = offer.get("attributes", {}).get("price")
    return price if isinstance(price, dict) else {}


def _order_lines(attributes: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten productList.categories[].products[] into one record per purchased line."""
    product_list = attributes.get("productList")
    categories = product_list.get("categories") if isinstance(product_list, dict) else None
    if not isinstance(categories, list):
        return []
    lines: list[dict[str, Any]] = []
    for category in categories:
        if not isinstance(category, dict):
            continue
        for product in category.get("products") or []:
            if not isinstance(product, dict):
                continue
            attrs = product.get("attributes") or {}
            quantity = attrs.get("quantity") or {}
            price = _first_offer_price(attrs)
            total = price.get("totalPrice") or {}
            lines.append(
                {
                    "ean": attrs.get("ean"),
                    "title": attrs.get("title"),
                    "brand": attrs.get("brand"),
                    "order_category_code": attrs.get("category"),
                    "order_line_index": attrs.get("orderLineIndex"),
                    "qty_requested": _as_float(quantity.get("requested")),
                    "qty_delivered": _as_float(quantity.get("delivered")),
                    "qty_refunded": _as_float(quantity.get("refunded")),
                    "unit_price": _as_float(price.get("price")),
                    "line_total": _as_float(total.get("requested")),
                    "immediate_discount": _as_float(total.get("immediateDiscount")),
                }
            )
    return lines


def _flatten_order(doc: dict[str, Any]) -> dict[str, Any]:
    """Build a clean order document (header + payments[] + lines[]) from the raw JSON."""
    attrs = doc.get("attributes") or {}
    slot = attrs.get("slot") or {}
    payments = [
        {"amount": _as_float(p.get("amount")), "date": p.get("date"), "choice": p.get("choice")}
        for p in (attrs.get("paymentInfos") or [])
        if isinstance(p, dict)
    ]
    return {
        "order_number": str(attrs.get("orderNumber")) if attrs.get("orderNumber") else None,
        "date": attrs.get("date"),
        "service_type": attrs.get("serviceType"),
        "delivery_channel": attrs.get("deliveryChannel"),
        "order_status": attrs.get("orderStatus"),
        "total_amount": _as_float(attrs.get("totalAmount")),
        "immediate_discount_amount": _as_float(attrs.get("immediateDiscountAmount")),
        "vat_at_20": _as_float(attrs.get("vatAt20")),
        "vat_at_5": _as_float(attrs.get("vatAt5")),
        "slot_date_begin": slot.get("dateBegin"),
        "slot_date_end": slot.get("dateEnd"),
        "payments": payments,
        "lines": _order_lines(attrs),
    }


def iter_order_files(source_dir: str | Path) -> Iterator[dict[str, Any]]:
    """Yield each flattened Drive order document found under ``source_dir``.

    Selects detail JSON docs carrying ``attributes.productList`` (orders); receipt
    details (top-level ``id``), loyalty months (``history``) and list pages are ignored.
    Dedups by ``order_number`` keeping the most recent file (timestamp-prefixed names).
    """
    source = Path(source_dir)
    if not source.exists():
        raise FileNotFoundError(f"Orders source directory not found: {source}")

    by_order: dict[str, dict[str, Any]] = {}
    for file in sorted(source.rglob("*.json")):
        try:
            doc = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("skipping_malformed_json", file=str(file), error=str(exc))
            continue
        attrs = doc.get("attributes") if isinstance(doc, dict) else None
        if not isinstance(attrs, dict) or "productList" not in attrs:
            continue
        flat = _flatten_order(doc)
        if not flat["order_number"]:
            logger.warning("skipping_order_without_number", file=str(file))
            continue
        by_order[flat["order_number"]] = flat  # later (more recent) file wins

    count = 0
    for order in by_order.values():
        count += 1
        yield order
    logger.info("orders_yielded", count=count, source=str(source))


@dlt.resource(name="orders", primary_key="order_number", write_disposition="merge")
def orders_resource(source_dir: str | Path) -> Iterator[dict[str, Any]]:
    """dlt resource streaming flattened Drive orders (merged on ``order_number``)."""
    yield from iter_order_files(source_dir)


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
    source_dir: str | Path | None = None,
    db_path: str | None = None,
    dataset: str | None = None,
    pipelines_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the dlt pipeline loading the loyalty JSON months into DuckDB."""
    source_dir = source_dir if source_dir is not None else config.LOYALTY_SOURCE_DIR
    db_path = db_path if db_path is not None else config.DUCKDB_PATH
    dataset = dataset if dataset is not None else config.DUCKDB_DATASET

    pipeline = _pipeline(db_path, dataset, pipelines_dir)
    info = pipeline.run(loyalty_resource(source_dir))
    logger.info("loyalty_load_complete", db_path=db_path, dataset=dataset)
    return {
        "db_path": db_path,
        "dataset": dataset,
        "row_counts": _row_counts(pipeline),
        "info": str(info),
    }


def load_orders(
    source_dir: str | Path | None = None,
    db_path: str | None = None,
    dataset: str | None = None,
    pipelines_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the dlt pipeline loading flattened Drive orders into DuckDB."""
    source_dir = source_dir if source_dir is not None else config.ORDERS_SOURCE_DIR
    db_path = db_path if db_path is not None else config.DUCKDB_PATH
    dataset = dataset if dataset is not None else config.DUCKDB_DATASET

    pipeline = _pipeline(db_path, dataset, pipelines_dir)
    info = pipeline.run(orders_resource(source_dir))
    logger.info("orders_load_complete", db_path=db_path, dataset=dataset)
    return {
        "db_path": db_path,
        "dataset": dataset,
        "row_counts": _row_counts(pipeline),
        "info": str(info),
    }


def load_all(
    source_dir: str | Path | None = None,
    loyalty_dir: str | Path | None = None,
    orders_dir: str | Path | None = None,
    db_path: str | None = None,
    dataset: str | None = None,
    pipelines_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Load receipts, loyalty and orders into the same ``raw`` dataset (one pipeline run)."""
    source_dir = source_dir if source_dir is not None else config.RECEIPTS_SOURCE_DIR
    loyalty_dir = loyalty_dir if loyalty_dir is not None else config.LOYALTY_SOURCE_DIR
    orders_dir = orders_dir if orders_dir is not None else config.ORDERS_SOURCE_DIR
    db_path = db_path if db_path is not None else config.DUCKDB_PATH
    dataset = dataset if dataset is not None else config.DUCKDB_DATASET

    pipeline = _pipeline(db_path, dataset, pipelines_dir)
    info = pipeline.run(
        [
            receipts_resource(source_dir),
            loyalty_resource(loyalty_dir),
            orders_resource(orders_dir),
        ]
    )
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
        help="Directory of loyalty JSON months (default: env LOYALTY_SOURCE_DIR).",
    )
    parser.add_argument(
        "--orders",
        default=None,
        help="Directory of Drive order JSON files (default: env ORDERS_SOURCE_DIR).",
    )
    parser.add_argument(
        "--no-loyalty", action="store_true", help="Load receipts only (skip loyalty + orders)."
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
            loyalty_dir=args.loyalty,
            orders_dir=args.orders,
            db_path=args.db,
            dataset=args.dataset,
            pipelines_dir=args.pipelines_dir,
        )
    logger.info("row_counts", **summary["row_counts"])
