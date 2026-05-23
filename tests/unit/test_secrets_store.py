"""Unit tests for the local secrets store (read/write data/secrets.yml)."""

import pytest

from carrefour_receipts_api.secrets_store import read_secrets, write_secrets

pytestmark = pytest.mark.fast


def test_read_missing_file_returns_empty(tmp_path):
    assert read_secrets(tmp_path / "nope.yml") == {}


def test_write_then_read_roundtrip(tmp_path):
    target = tmp_path / "nested" / "secrets.yml"
    write_secrets(target, loyaltyCardNumber="12345", passCardNumber="67890")
    assert read_secrets(target) == {"loyaltyCardNumber": "12345", "passCardNumber": "67890"}


def test_write_merges_and_preserves_existing_keys(tmp_path):
    target = tmp_path / "secrets.yml"
    write_secrets(target, loyaltyCardNumber="111", passCardNumber="222")
    write_secrets(target, loyaltyCardNumber="999")  # update one, leave the other
    assert read_secrets(target) == {"loyaltyCardNumber": "999", "passCardNumber": "222"}


def test_write_ignores_empty_fields(tmp_path):
    target = tmp_path / "secrets.yml"
    write_secrets(target, loyaltyCardNumber="111", passCardNumber="222")
    write_secrets(target, loyaltyCardNumber="", passCardNumber="   ")  # blanks: no-op
    assert read_secrets(target) == {"loyaltyCardNumber": "111", "passCardNumber": "222"}


def test_read_malformed_yaml_returns_empty(tmp_path):
    target = tmp_path / "secrets.yml"
    target.write_text("just: a: broken: mapping:\n  - [", encoding="utf-8")
    assert read_secrets(target) == {}
