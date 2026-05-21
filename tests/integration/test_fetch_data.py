"""
Test cases for the CarrefourUserAPIHandler's fetch_data method with different arguments.
Note: Those tests are there to detect any API key changes.
TODO: test SeleniumBase
"""

from datetime import datetime, timedelta
import pytest

# from unittest.mock import patch, MagicMock
from carrefour_receipts_api.user_api_extractor import (
    CarrefourUserAPIHandler,
    CarrefourAccountLogin,
)


@pytest.fixture
def handler():
    """Fixture to create an instance of CarrefourUserAPIHandler."""
    return CarrefourUserAPIHandler(cookies_file="cookies.txt", dst_folder="data")

@pytest.mark.fast
def test_fetch_receipts_list_one_scroll(handler: CarrefourUserAPIHandler):
    """
    Test the fetch_data method with a single scroll.
    """
    config = CarrefourAccountLogin.load_secrets()
    params_loyalty = {
        "loyaltyCardNumber": config.get("loyaltyCardNumber"),
        "loyaltyCardType": "LOYALTY",
    }
    api_url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
    try:
        data = handler.fetch_data(
            api_url,
            params_loyalty,
            referer=CarrefourUserAPIHandler.BRAND_REFERER.get("referer_store", ""),
            verbose=False,
        )
    except Exception as e:
        pytest.fail(f"Failed to fetch data: {e}")
    assert isinstance(data, dict)
    assert "data" in data
    assert "scrollPaging" in data["meta"]  # assume there is necessary history of data
    assert "scrollHash" in data["meta"]


@pytest.mark.parametrize(
    "scrollPaging, scrollHash, expected",
    [
        (
            "1030550609885801100%239223370342573875807",
            "06b66bb0d75c0e377a9d6e995b0d07814615ec3d",
            True,
        ),
        (
            "1030550609885801100%239223370382245035807",
            "8c620011e2b74cd88cc8caf46f21c8e0c4344d97",
            True,
        ),
        ("1030550609885801100%239223370382245035807", "invalid_hash", False),
    ],
)
@pytest.mark.fast
def test_fetch_receipts_list_second_scroll(
    handler: CarrefourUserAPIHandler, scrollPaging: str, scrollHash: str, expected: bool
):
    """
    Test the fetch_data method with a single scroll.
    Args:
        scrollPaging (str): The scrollPaging parameter to use in the request.
        scrollHash (str): The scrollHash parameter to use in the request.
        expected (bool): Whether the response is expected to contain data.
    Note: The scrollPaging is always the same, but the scrollHash may be different (dynamic?).
    """
    config = CarrefourAccountLogin.load_secrets()
    params_loyalty = {
        "loyaltyCardNumber": config.get("loyaltyCardNumber"),
        "loyaltyCardType": "LOYALTY",
    }
    params = {
        **params_loyalty,
        "scrollPaging": scrollPaging,
        "scrollHash": scrollHash,
    }
    api_url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
    try:
        data = handler.fetch_data(
            api_url,
            params,
            referer=CarrefourUserAPIHandler.BRAND_REFERER.get("referer_store", ""),
            verbose=False,
        )
    except Exception as e:
        pytest.fail(f"Failed to fetch data: {e}")

    assert isinstance(data, dict)
    if expected:
        assert "data" in data
        assert "scrollPaging" in data.get("meta")
        assert "scrollHash" in data.get("meta")
    else:
        assert "data" not in data


@pytest.fixture
def date_alternative_gap_check_fixture(request: pytest.FixtureRequest):
    date_str_alternative = request.param  # Unpack parameters passed to the fixture
    return date_alternative_gap_check(date_str_alternative)


def date_alternative_gap_check(date_str_alternative: str):
    """
    Check if a given date is less than one year ago from today.
    This function is used to demonstrate the date comparison logic.
    """
    # Get today's date
    today = datetime.today()
    month = int(date_str_alternative[:2])
    year = int(date_str_alternative[-4:])

    current_date = datetime(year=year, month=month, day=1)
    # Calculate the date one year ago (approximation using 365 days)
    one_year_ago = today - timedelta(days=365)
    # Check if the given date is less than one year ago
    return (current_date > one_year_ago) and (current_date <= today)


@pytest.mark.parametrize(
    "date_alternative_str, date_alternative_gap_check_fixture",
    [
        ("02/01/2025", "02/01/2025"),
        ("08/01/2025", "08/01/2025"),
        ("08/01/2024", "08/01/2024"),
        ("02/01/2024", "02/01/2024"),
        ("02/01/2023", "02/01/2023"),
    ],
    indirect=["date_alternative_gap_check_fixture"],
)
@pytest.mark.fast
def test_fetch_loyalty_lists(
    handler: CarrefourUserAPIHandler,
    date_alternative_str: str,
    date_alternative_gap_check_fixture: bool,
):
    """
    Tests the fetch_data method for fetching loyalty lists.
    """
    api_url = "https://www.carrefour.fr/api/user/secured/loyalty/transactions"

    if not date_alternative_str:
        raise ValueError("The date is None.")
    month = int(date_alternative_str[:2])
    year = int(date_alternative_str[-4:])

    current_date = datetime(
        year=year, month=month, day=1
    )  # Start with the initial date
    params = {
        "date": current_date.strftime(
            "%m/01/%Y"
        )  # Use strftime for consistent formatting
    }

    data = handler.fetch_data(
        api_url,
        params,
        referer=CarrefourUserAPIHandler.BRAND_REFERER.get("referer_loyalty", ""),
        verbose=False,
    )
    expected = date_alternative_gap_check_fixture
    if expected:
        assert isinstance(data, dict)
        assert "history" in data, "History should be present in the data"
        assert isinstance(
            data.get("history", [{}])[0].get("earned"), float
        ), "Earned should be a float"
    else:
        assert isinstance(data, dict)
        assert "history" in data, "History should still be present in the data despite the date being more than a year ago"
        assert not data.get("history"), "History should be empty when the date is more than a year ago"
