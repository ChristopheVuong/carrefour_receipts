"""Unit tests for the my-cards card-number parser (pure, no browser/network)."""

import pytest

from carrefour_receipts_api.auth_service.browser import parse_card_numbers

pytestmark = pytest.mark.fast


def test_parses_both_cards_from_my_cards_payload():
    # Real shape of GET /api/user/secured/loyalty/my-cards.
    payload = {
        "id": None,
        "type": "loyaltyCardList",
        "attributes": [
            {"loyaltyCardNumber": "0000005422294", "loyaltyCardType": "LOYALTY"},
            {"loyaltyCardNumber": "1030550609885801100", "loyaltyCardType": "PASS_MASTERCARD"},
        ],
    }
    assert parse_card_numbers(payload) == {
        # LOYALTY gets the "913572" Carte Carrefour prefix -> full receipt-form barcode.
        "loyaltyCardNumber": "9135720000005422294",
        "passCardNumber": "1030550609885801100",  # PASS left as-is
    }


def test_loyalty_prefix_is_idempotent():
    # If my-cards ever returns the already-prefixed number, don't double-prefix it.
    payload = {
        "attributes": [{"loyaltyCardNumber": "9135720000005422294", "loyaltyCardType": "LOYALTY"}]
    }
    assert parse_card_numbers(payload)["loyaltyCardNumber"] == "9135720000005422294"


def test_pass_only_payload():
    payload = {
        "attributes": [
            {"loyaltyCardNumber": "1030550609885801100", "loyaltyCardType": "PASS_MASTERCARD"},
        ]
    }
    cards = parse_card_numbers(payload)
    assert cards["passCardNumber"] == "1030550609885801100"
    assert cards["loyaltyCardNumber"] is None


def test_first_card_of_a_type_wins():
    payload = {
        "attributes": [
            {"loyaltyCardNumber": "0000000000111", "loyaltyCardType": "LOYALTY"},
            {"loyaltyCardNumber": "0000000000222", "loyaltyCardType": "LOYALTY"},
        ]
    }
    assert parse_card_numbers(payload)["loyaltyCardNumber"] == "9135720000000000111"


def test_tolerates_api_me_number_type_schema():
    # Fallback shape (number/type) is still understood if Carrefour changes endpoints.
    payload = {"loyaltyCard": {"number": "1030550609885801100", "type": "PASS_MASTERCARD"}}
    assert parse_card_numbers(payload)["passCardNumber"] == "1030550609885801100"


def test_missing_cards_yield_none():
    assert parse_card_numbers({"type": "loyaltyCardList", "attributes": []}) == {
        "loyaltyCardNumber": None,
        "passCardNumber": None,
    }


def test_robust_to_non_dict_input():
    assert parse_card_numbers([]) == {"loyaltyCardNumber": None, "passCardNumber": None}
