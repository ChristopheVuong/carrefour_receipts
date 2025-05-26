import pytest
from unittest.mock import patch, MagicMock
from src.user_api_extractor import CarrefourAccountAPIHandler  # Replace with the actual module name

@pytest.fixture
def handler():
    """Fixture to create an instance of CarrefourAccountAPIHandler."""
    return CarrefourAccountAPIHandler(cookies_file="dummy_cookies.txt", dst_folder="dummy_folder")

def test_fetch_data_success(handler):
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
        result = handler.fetch_data(url, params, referer, verbose)

        # Assertions
        mock_run.assert_called_once()  # Ensure subprocess.run was called
        assert result == {"key": "value"}  # Check the parsed JSON response

def test_fetch_data_error(handler):
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
            handler.fetch_data(url, params, referer, verbose)

        # Assertions
        mock_run.assert_called_once()  # Ensure subprocess.run was called
        assert "Failed to fetch API data" in str(exc_info.value)  # Check the error message

def test_fetch_data_invalid_json(handler):
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
            handler.fetch_data(url, params, referer, verbose)

        # Assertions
        mock_run.assert_called_once()  # Ensure subprocess.run was called
        assert "JSONDecodeError" in str(exc_info.value)  # Check the error message