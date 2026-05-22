"""Unit tests for the synthetic loyalty merge key built in the dlt load.

A loyalty line has no natural key, so ``iter_loyalty_rows`` derives a
deterministic ``loyalty_row_key`` = ``sha1(content signature | occurrence)``.
These tests pin the two properties the merge relies on:

  - the same physical row yields the same key across loads (dedup), and
  - legitimately duplicate lines in one operation get distinct keys (occurrence).
"""

from pathlib import Path

import pytest

from carrefour_receipts_api.elt.load import _canon, iter_loyalty_rows

pytestmark = pytest.mark.fast

_HEADER = "operationId,date,earned,burned,itemLabel,promotionLabel,itemRd,loyaltyOperation\n"


def _keys(tmp_path: Path, body: str, name: str = "loyalty.csv") -> list[str]:
    csv = tmp_path / name
    csv.write_text(_HEADER + body, encoding="utf-8")
    return [row["loyalty_row_key"] for row in iter_loyalty_rows(csv)]


def test_key_is_deterministic_across_loads(tmp_path):
    body = "111,2024-01-15,0.21,0.0,BANANE BIO,,0.10,Paiement en caisse\n"
    assert _keys(tmp_path, body, "a.csv") == _keys(tmp_path, body, "b.csv")


def test_identical_lines_get_distinct_keys(tmp_path):
    row = "111,2024-01-15,0.21,0.0,BANANE BIO,,0.10,Paiement en caisse\n"
    keys = _keys(tmp_path, row + row)  # two identical bananas in one operation
    assert len(keys) == 2
    assert keys[0] != keys[1]  # occurrence index keeps them distinct


def test_different_content_gives_different_keys(tmp_path):
    body = (
        "111,2024-01-15,0.21,0.0,BANANE BIO,,0.10,Paiement en caisse\n"
        "111,2024-01-15,0.05,0.0,LAIT DEMI-ECREME 1L,,0.00,Paiement en caisse\n"
    )
    keys = _keys(tmp_path, body)
    assert keys[0] != keys[1]


def test_key_insensitive_to_float_formatting(tmp_path):
    a = _keys(tmp_path, "111,2024-01-15,0.10,0.0,BANANE,,0.0,Caisse\n", "a.csv")
    b = _keys(tmp_path, "111,2024-01-15,0.1,0.00,BANANE,,0.000,Caisse\n", "b.csv")
    assert a == b  # "0.10" and "0.1" canonicalize to the same amount


@pytest.mark.parametrize(
    "value, expected",
    [(None, ""), ("", ""), ("  x ", "x"), (0.1, "0.1000"), (0.0, "0.0000")],
)
def test_canon_normalizes_fields(value, expected):
    assert _canon(value) == expected
