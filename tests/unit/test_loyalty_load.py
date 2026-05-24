"""Unit tests for the loyalty JSON discovery (pure, no dlt/network)."""

import json

import pytest

from carrefour_receipts_api.elt.load import _to_float, iter_loyalty_files

pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    "value, expected",
    [
        ("0.21", 0.21),
        ("0,21", 0.21),  # French decimal comma
        ("3,00", 3.0),
        ("  1,5 ", 1.5),
        ("", None),
        ("   ", None),
        (None, None),
        ("nan-ish", None),
    ],
)
def test_to_float_handles_comma_decimals(value, expected):
    assert _to_float(value) == expected


def _write(path, doc):
    path.write_text(json.dumps(doc), encoding="utf-8")


def _month(month, store="STORE", earned=0.1):
    return {
        "_id": month,
        "history": [
            {
                "operationId": month,
                "date": f"{month[:4]}-{month[4:]}-15",
                "store": store,
                "earned": earned,
                "burned": 0.0,
                "canceled": False,
            },
        ],
    }


def test_selects_only_history_docs(tmp_path):
    _write(tmp_path / "m.json", _month("202401"))
    _write(tmp_path / "receipt.json", {"id": "store_x", "attributes": {}})  # ticket detail
    _write(tmp_path / "scroll.json", {"data": [], "meta": {}})  # list page, no id/history

    docs = list(iter_loyalty_files(tmp_path))
    assert len(docs) == 1
    assert docs[0]["_id"] == "202401"


def test_coerces_french_comma_amounts(tmp_path):
    doc = _month("202401")
    doc["history"][0]["earned"] = "0,21"
    _write(tmp_path / "m.json", doc)

    [out] = list(iter_loyalty_files(tmp_path))
    assert out["history"][0]["earned"] == 0.21


def test_dedups_by_month_keeping_most_recent_file(tmp_path):
    # Same _id in two files; the lexicographically-later (more recent timestamp) wins.
    _write(tmp_path / "20240101_00_00-loyalty.json", _month("202401", store="OLD"))
    _write(tmp_path / "20240601_00_00-loyalty.json", _month("202401", store="NEW"))

    docs = list(iter_loyalty_files(tmp_path))
    assert len(docs) == 1
    assert docs[0]["history"][0]["store"] == "NEW"


def test_skips_history_doc_without_id(tmp_path):
    _write(tmp_path / "no_id.json", {"history": [{"operationId": "1"}]})
    assert list(iter_loyalty_files(tmp_path)) == []


def test_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(iter_loyalty_files(tmp_path / "nope"))
