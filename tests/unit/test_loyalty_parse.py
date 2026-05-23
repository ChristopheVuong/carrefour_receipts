"""Unit tests for the /api/me card-number parser (pure, no browser/network)."""

import pytest

from carrefour_receipts_api.auth_service.browser import parse_card_numbers

pytestmark = pytest.mark.fast


def test_parses_pass_card_from_loyalty_card_object():
    me = {
        "firstName": "X",
        "loyaltyCard": {
            "number": "1030550609885801100",
            "type": "PASS_MASTERCARD",
            "isSecured": True,
        },
    }
    cards = parse_card_numbers(me)
    assert cards["passCardNumber"] == "1030550609885801100"
    assert cards["loyaltyCardNumber"] is None


def test_parses_both_types_from_a_list():
    me = {
        "loyaltyCards": [
            {"number": "9135720000005422294", "type": "LOYALTY"},
            {"number": "1030550609885801100", "type": "PASS_MASTERCARD"},
        ]
    }
    assert parse_card_numbers(me) == {
        "loyaltyCardNumber": "9135720000005422294",
        "passCardNumber": "1030550609885801100",
    }


def test_first_card_of_a_type_wins():
    me = {
        "cards": [
            {"number": "111", "type": "LOYALTY"},
            {"number": "222", "type": "LOYALTY"},
        ]
    }
    assert parse_card_numbers(me)["loyaltyCardNumber"] == "111"


def test_missing_cards_yield_none():
    assert parse_card_numbers({"firstName": "X"}) == {
        "loyaltyCardNumber": None,
        "passCardNumber": None,
    }


def test_robust_to_non_dict_input():
    assert parse_card_numbers([]) == {"loyaltyCardNumber": None, "passCardNumber": None}
