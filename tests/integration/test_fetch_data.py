"""
Integration tests for the Carrefour extractors' ``fetch_data`` method.

These hit the *live* Carrefour API and therefore require:
  - a valid ``data/cookies.txt`` exported from an authenticated browser session;
  - a ``data/secrets.yml`` holding at least ``loyaltyCardNumber``.

They are marked ``integration`` and skipped automatically when those
prerequisites are missing (e.g. in CI). Their purpose is to detect breaking
changes in the hidden API contract (parameters, pagination keys, payload shape).
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from carrefour_receipts_api.login import AccountLogin
from carrefour_receipts_api.user_api_extractor import (
    CarrefourLoyaltyExtractor,
    CarrefourReceiptExtractor,
)

pytestmark = pytest.mark.integration

DATA_DIRECTORY = "data"
COOKIES_FILE = f"{DATA_DIRECTORY}/cookies.txt"
SECRETS_FILE = f"{DATA_DIRECTORY}/secrets.yml"

# Skip the whole module unless live credentials are available locally.
if not (Path(COOKIES_FILE).exists() and Path(SECRETS_FILE).exists()):
    pytest.skip(
        "Live Carrefour credentials missing "
        f"({COOKIES_FILE} and/or {SECRETS_FILE}); skipping integration tests.",
        allow_module_level=True,
    )


@pytest.fixture
def receipt_extractor() -> CarrefourReceiptExtractor:
    """Receipt extractor wired to the local cookies file."""
    return CarrefourReceiptExtractor(cookies_file=COOKIES_FILE, dst_folder=DATA_DIRECTORY)


@pytest.fixture
def loyalty_extractor() -> CarrefourLoyaltyExtractor:
    """Loyalty extractor wired to the local cookies file."""
    return CarrefourLoyaltyExtractor(cookies_file=COOKIES_FILE, dst_folder=DATA_DIRECTORY)


@pytest.fixture
def loyalty_params() -> dict[str, str]:
    config = AccountLogin.load_secrets(path_to_secrets=SECRETS_FILE)
    return {
        "loyaltyCardNumber": config.get("loyaltyCardNumber"),
        "loyaltyCardType": "LOYALTY",
    }


def test_fetch_receipts_list_one_scroll(
    receipt_extractor: CarrefourReceiptExtractor, loyalty_params: dict[str, str]
):
    """The first receipts page returns data plus pagination cursors."""
    try:
        data = receipt_extractor.fetch_data(
            CarrefourReceiptExtractor.API_URL,
            loyalty_params,
            referer=CarrefourReceiptExtractor.REFERER_URL,
            verbose=False,
        )
    except Exception as e:  # pragma: no cover - network failure path
        pytest.fail(f"Failed to fetch data: {e}")
    assert isinstance(data, dict)
    assert "data" in data
    assert "scrollPaging" in data["meta"]
    assert "scrollHash" in data["meta"]


@pytest.mark.parametrize(
    "scroll_paging, scroll_hash, expected",
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
def test_fetch_receipts_list_second_scroll(
    receipt_extractor: CarrefourReceiptExtractor,
    loyalty_params: dict[str, str],
    scroll_paging: str,
    scroll_hash: str,
    expected: bool,
):
    """Subsequent pages are driven by the ``scrollPaging``/``scrollHash`` cursors."""
    params = {**loyalty_params, "scrollPaging": scroll_paging, "scrollHash": scroll_hash}
    try:
        data = receipt_extractor.fetch_data(
            CarrefourReceiptExtractor.API_URL,
            params,
            referer=CarrefourReceiptExtractor.REFERER_URL,
            verbose=False,
        )
    except Exception as e:  # pragma: no cover - network failure path
        pytest.fail(f"Failed to fetch data: {e}")

    assert isinstance(data, dict)
    if expected:
        assert "data" in data
        assert "scrollPaging" in data.get("meta", {})
        assert "scrollHash" in data.get("meta", {})
    else:
        assert "data" not in data


def _date_within_last_year(date_str: str) -> bool:
    """True when ``MM/01/YYYY`` is within the last 365 days and not in the future."""
    month, year = int(date_str[:2]), int(date_str[-4:])
    current_date = datetime(year=year, month=month, day=1)
    one_year_ago = datetime.today() - timedelta(days=365)
    return one_year_ago < current_date <= datetime.today()


@pytest.mark.parametrize(
    "date_str",
    ["02/01/2025", "08/01/2025", "08/01/2024", "02/01/2024", "02/01/2023"],
)
def test_fetch_loyalty_lists(loyalty_extractor: CarrefourLoyaltyExtractor, date_str: str):
    """Loyalty history is only returned for dates within the last year."""
    month, year = int(date_str[:2]), int(date_str[-4:])
    params = {"date": datetime(year=year, month=month, day=1).strftime("%m/01/%Y")}

    data = loyalty_extractor.fetch_data(
        CarrefourLoyaltyExtractor.API_URL,
        params,
        referer=CarrefourLoyaltyExtractor.REFERER_URL,
        verbose=False,
    )

    assert isinstance(data, dict)
    assert "history" in data
    if _date_within_last_year(date_str):
        assert isinstance(data.get("history", [{}])[0].get("earned"), float)
    else:
        assert not data.get("history")
