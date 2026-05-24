"""Unit tests for the auth-service account (loyalty/Pass card) endpoints."""

import pytest

pytestmark = pytest.mark.fast

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from carrefour_receipts_api import config  # noqa: E402
from carrefour_receipts_api.auth_service.app import app  # noqa: E402
from carrefour_receipts_api.secrets_store import read_secrets  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SECRETS_FILE", str(tmp_path / "secrets.yml"))
    monkeypatch.delenv("LOYALTY_CARD_NUMBER", raising=False)
    monkeypatch.delenv("PASS_CARD_NUMBER", raising=False)
    return TestClient(app)


def test_post_account_writes_secrets(client):
    resp = client.post(
        "/account",
        data={"loyalty_card_number": "64070450001234", "pass_card_number": "0550609885801100"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["loyalty_present"] is True and body["pass_present"] is True
    assert read_secrets(config.SECRETS_FILE) == {
        "loyaltyCardNumber": "64070450001234",
        "passCardNumber": "0550609885801100",
    }


def test_post_account_partial_does_not_wipe(client):
    client.post("/account", data={"loyalty_card_number": "111", "pass_card_number": "222"})
    client.post("/account", data={"loyalty_card_number": "999", "pass_card_number": ""})
    assert read_secrets(config.SECRETS_FILE) == {
        "loyaltyCardNumber": "999",
        "passCardNumber": "222",
    }


def test_index_shows_loyalty_card(client):
    client.post("/account", data={"loyalty_card_number": "64070450001234"})
    html = client.get("/").text
    assert "Loyalty / fidélité card" in html
    assert "64070450001234" in html
