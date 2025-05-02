import pytest
import os
import json
from unittest.mock import patch, MagicMock
from typing import Dict, Any

import subprocess

# Assuming fetch_api_data is defined in a module named `api_fetcher`
from user_api_extractor import fetch_list_receipts

@pytest.fixture
def mock_cookies_file(tmp_path):
    """Fixture to create a temporary cookies file."""
    cookies_file = tmp_path / "cookies.txt"
    cookies_file.write_text("test_cookie_data")
    return str(cookies_file)

@patch("subprocess.run")
def test_fetch_api_data_success(mock_subprocess_run, mock_cookies_file, caplog):
    """
    Test successful API data fetch with valid cookies.
    """
    # Mock subprocess.run to return a successful response
    mock_subprocess_run.return_value = MagicMock(
        stdout=json.dumps({"status": "success", "data": {"key": "value"}}),
        stderr="",
        returncode=0
    )

    # Call the function
    url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
    params = {"scrollPaging": "9135720000005422294%25239223370309338615807", "scrollHash": "1ced8cd234aead22ebca28defa83d3c35ddb3d70"}
    result = fetch_list_receipts(url, params, cookies_file=mock_cookies_file)

    # Assertions
    assert isinstance(result, dict), "Result should be a dictionary"
    assert "status" in result and result["status"] == "success", "Response should contain 'status': 'success'"
    assert "data" in result and result["data"] == {"key": "value"}, "Response data should match expected value"
    assert "Parsed JSON Data:" in caplog.text, "Log should indicate successful JSON parsing"

@patch("subprocess.run")
def test_fetch_api_data_json_decode_error(mock_subprocess_run, mock_cookies_file, caplog):
    """
    Test handling of JSONDecodeError when the API returns invalid JSON.
    """
    # Mock subprocess.run to return invalid JSON
    mock_subprocess_run.return_value = MagicMock(
        stdout="invalid_json",
        stderr="",
        returncode=0
    )

    # Call the function
    url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
    params = {"scrollPaging": "9135720000005422294%25239223370309338615807", "scrollHash": "1ced8cd234aead22ebca28defa83d3c35ddb3d70"}

    with pytest.raises(json.JSONDecodeError):
        fetch_list_receipts(url, params, cookies_file=mock_cookies_file)

    # Assertions
    assert "Failed to parse JSON" in caplog.text, "Log should indicate JSON parsing failure"

@patch("os.path.exists")
def test_fetch_api_data_file_not_found(mock_exists, caplog):
    """
    Test FileNotFoundError when cookies file does not exist.
    """
    # Mock os.path.exists to return False
    mock_exists.return_value = False

    # Call the function
    url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
    params = {"scrollPaging": "9135720000005422294%25239223370309338615807", "scrollHash": "1ced8cd234aead22ebca28defa83d3c35ddb3d70"}

    with pytest.raises(FileNotFoundError) as exc_info:
        fetch_list_receipts(url, params, cookies_file="nonexistent_cookies.txt")

    # Assertions
    assert "Cookies file not found" in str(exc_info.value), "Error message should indicate missing cookies file"
    assert "Cookies file not found" in caplog.text, "Log should indicate missing cookies file"

@patch("subprocess.run")
def test_fetch_api_data_subprocess_error(mock_subprocess_run, mock_cookies_file, caplog):
    """
    Test handling of subprocess.CalledProcessError.
    """
    # Mock subprocess.run to raise CalledProcessError
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["curl", "-X", "GET", "..."],
        output="Error occurred",
        stderr="Subprocess failed"
    )

    # Call the function
    url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
    params = {"scrollPaging": "9135720000005422294%25239223370309338615807", "scrollHash": "1ced8cd234aead22ebca28defa83d3c35ddb3d70"}

    with pytest.raises(subprocess.CalledProcessError):
        fetch_list_receipts(url, params, cookies_file=mock_cookies_file)

    # Assertions
    assert "Failed to fetch API data" in caplog.text, "Log should indicate subprocess failure"