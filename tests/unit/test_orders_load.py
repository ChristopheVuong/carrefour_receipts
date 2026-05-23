"""Unit tests for the Drive order flatten + discovery (pure, no dlt/network)."""

import json

import pytest

from carrefour_receipts_api.elt.load import _flatten_order, iter_order_files

pytestmark = pytest.mark.fast


def _order(number="1", *, lines, payments=None):
    """Build a raw order doc (nested productList/offers) for one category of lines."""
    products = []
    for i, ln in enumerate(lines):
        ean = ln["ean"]
        products.append(
            {
                "type": "product",
                "id": str(i),
                "attributes": {
                    "ean": ean,
                    "title": ln["title"],
                    "brand": ln.get("brand", ""),
                    "category": "CAT",
                    "orderLineIndex": i,
                    "quantity": {"requested": ln["qty"], "delivered": ln["qty"], "refunded": 0},
                    "offers": {
                        ean: {
                            f"off-{i}": {
                                "type": "offer",
                                "attributes": {
                                    "price": {
                                        "price": ln["unit"],
                                        "totalPrice": {
                                            "requested": ln["total"],
                                            "immediateDiscount": ln.get("disc", 0.0),
                                        },
                                    }
                                },
                            }
                        }
                    },
                },
            }
        )
    return {
        "attributes": {
            "orderNumber": number,
            "date": "2024-01-20 10:15:00",
            "serviceType": "PICKING_DRIVE",
            "deliveryChannel": "DRIVE",
            "orderStatus": "RECEPTIONNEE",
            "totalAmount": 7.5,
            "immediateDiscountAmount": 1.0,
            "vatAt20": 2.0,
            "vatAt5": 0,
            "slot": {"dateBegin": "2024-01-21 16:30:00", "dateEnd": "2024-01-21 17:00:00"},
            "paymentInfos": payments
            or [{"amount": 7.5, "date": "2024-01-20T10:15:00+01:00", "choice": "CB"}],
            "productList": {"categories": [{"name": "CAT", "products": products}]},
        }
    }


def test_flatten_pulls_lines_and_price_from_nested_offers():
    doc = _order(
        "100000001",
        lines=[
            {"ean": "1", "title": "BANANE", "qty": 2, "unit": 1.5, "total": 3.0},
            {"ean": "2", "title": "POMME", "qty": 1, "unit": 2.5, "total": 2.5, "disc": 1.0},
        ],
    )
    flat = _flatten_order(doc)
    assert flat["order_number"] == "100000001"
    assert len(flat["lines"]) == 2
    banane = flat["lines"][0]
    assert banane["title"] == "BANANE"
    assert banane["unit_price"] == 1.5
    assert banane["line_total"] == 3.0
    assert flat["lines"][1]["immediate_discount"] == 1.0
    assert flat["payments"][0]["choice"] == "CB"
    # vatAt5 was an int 0 → coerced to float so dlt types it DOUBLE.
    assert isinstance(flat["vat_at_5"], float)


def test_flatten_tolerates_missing_offer_price():
    doc = _order("1", lines=[{"ean": "1", "title": "X", "qty": 1, "unit": 1.0, "total": 1.0}])
    # Strip the offers entirely → price fields become None, line still kept.
    doc["attributes"]["productList"]["categories"][0]["products"][0]["attributes"]["offers"] = {}
    flat = _flatten_order(doc)
    assert len(flat["lines"]) == 1
    assert flat["lines"][0]["unit_price"] is None


def test_iter_order_files_selects_orders_only(tmp_path):
    (tmp_path / "order.json").write_text(
        json.dumps(
            _order(
                "100000001", lines=[{"ean": "1", "title": "X", "qty": 1, "unit": 1.0, "total": 1.0}]
            )
        ),
        encoding="utf-8",
    )
    (tmp_path / "receipt.json").write_text(
        json.dumps({"id": "store_x", "attributes": {}}), encoding="utf-8"
    )
    (tmp_path / "loyalty.json").write_text(
        json.dumps({"_id": "202401", "history": []}), encoding="utf-8"
    )
    (tmp_path / "scroll.json").write_text(json.dumps({"data": [], "meta": {}}), encoding="utf-8")

    orders = list(iter_order_files(tmp_path))
    assert [o["order_number"] for o in orders] == ["100000001"]


def test_iter_order_files_dedups_by_order_number(tmp_path):
    old = _order(
        "100000001", lines=[{"ean": "1", "title": "OLD", "qty": 1, "unit": 1.0, "total": 1.0}]
    )
    new = _order(
        "100000001", lines=[{"ean": "1", "title": "NEW", "qty": 1, "unit": 1.0, "total": 1.0}]
    )
    (tmp_path / "20240101_00_00-order.json").write_text(json.dumps(old), encoding="utf-8")
    (tmp_path / "20240601_00_00-order.json").write_text(json.dumps(new), encoding="utf-8")

    orders = list(iter_order_files(tmp_path))
    assert len(orders) == 1
    assert orders[0]["lines"][0]["title"] == "NEW"


def test_iter_order_files_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(iter_order_files(tmp_path / "nope"))
