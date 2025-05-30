"""
Test cases for the CarrefourAccountAPIHandler's fetch_data method with mock.
Note: This code may be useful because the fetching part is not the essential added value of the library.
Test 
"""
import pytest
from unittest.mock import patch, MagicMock
from src.carrefour_receipts_api.user_api_extractor import CarrefourAccountAPIHandler  # Replace with the actual module name

@pytest.fixture
def handler_mock():
    """Fixture to create an instance of CarrefourAccountAPIHandler."""
    return CarrefourAccountAPIHandler(cookies_file="dummy_cookies.txt", dst_folder="dummy_folder")

def test_fetch_data_success(handler_mock):
    """
    Test the fetch_data method when the curl command is successful.
    """
    # Mock subprocess.run to simulate a successful curl command
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"key": "value"}'
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        url = "https://example.com/api "
        params = {"param1": "value1"}
        referer = "https://example.com "
        verbose = False

        # Call the fetch_data method
        result = handler_mock.fetch_data(url, params, referer, verbose)

        # Assertions
        mock_run.assert_called_once()  # Ensure subprocess.run was called
        assert result == {"key": "value"}  # Check the parsed JSON response

def test_fetch_data_error(handler_mock):
    """
    Test the fetch_data method when the curl command fails.
    """
    # Mock subprocess.run to simulate a failed curl command
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Error: Failed to fetch data"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        url = "https://example.com/api "
        params = {"param1": "value1"}
        referer = "https://example.com "
        verbose = False

        # Call the fetch_data method and expect it to raise an exception
        with pytest.raises(Exception) as exc_info:
            handler_mock.fetch_data(url, params, referer, verbose)

        # Assertions
        mock_run.assert_called_once()  # Ensure subprocess.run was called
        assert "Failed to fetch API data" in str(exc_info.value)  # Check the error message

def test_fetch_data_invalid_json(handler_mock):
    """
    Test the fetch_data method when the curl command returns invalid JSON.
    """
    # Mock subprocess.run to simulate a successful curl command with invalid JSON
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "invalid json"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        url = "https://example.com/api "
        params = {"param1": "value1"}
        referer = "https://example.com "
        verbose = False

        # Call the fetch_data method and expect it to raise an exception
        with pytest.raises(Exception) as exc_info:
            handler_mock.fetch_data(url, params, referer, verbose)

        # Assertions
        mock_run.assert_called_once()  # Ensure subprocess.run was called
        assert "JSONDecodeError" in str(exc_info.value)  # Check the error message

  
@pytest.fixture
def handler():
    """Fixture to create an instance of CarrefourAccountAPIHandler."""
    return CarrefourAccountAPIHandler(cookies_file="cookies.txt", dst_folder="data")


def fetch_data_one_scroll(handler):
    """
    Test the fetch_data method with a single scroll.
    TODO: Write the whole test with two case one without params scrollHash, the other with it.
    """
    config = CarrefourAccountAPIHandler.load_secrets()
    params_loyalty = {
        "loyaltyCardNumber": config.get("loyaltyCardNumber"),
        "loyaltyCardType": "LOYALTY",
    }
    api_url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
    handler.fetch_data(api_url, params_loyalty, referer=CarrefourAccountAPIHandler.BRAND_NAME.get("referer_store", ""), verbose=False)


