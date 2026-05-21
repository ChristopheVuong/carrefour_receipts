from abc import ABC, abstractmethod
import logging
from typing import Dict, Any
import subprocess
from pathlib import Path
from urllib.parse import unquote

import yaml

from carrefour_receipts_api import config

# Configure logging (logging to console or in log file)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATA_DIRECTORY = config.DATA_DIRECTORY  # from env / .env (default: "data")
COOKIES_FILE = config.COOKIES_FILE  # path to the cookies file (from env / .env)

class AccountLogin(ABC):
    """
    Abstract base class for handling account login operations.
    This class should be extended to implement specific login mechanisms.
    """

    def __init__(self, *args, **kwargs) -> None:
        """
        Perform login using curl and save cookies to a file.
        Supports multiple input formats for credentials.
        Args:
            *args: Positional arguments (e.g., a dictionary for user_id).
            **kwargs: Keyword arguments (e.g., username and password).
        Raises:
            ValueError: If no valid input is provided.
            KeyError: If required keys are missing in the dictionary.
            subprocess.CalledProcessError: If the curl command fails.
        Note: This method does not bypass Cloudfare turnstile anti-bot protection.
        The same goes for Selenium, Playwright (cf_waiting_room remain). Use a browser instead.
        """

        # Extract credentials based on input format
        if args and isinstance(args[0], dict):
            user_id = args[0]
            if "username" not in user_id or "password" not in user_id:
                raise KeyError(
                    "Missing required keys in user_id: 'username' and/or 'password'"
                )
            username, password = user_id["username"], user_id["password"]
        elif kwargs:
            username = kwargs.get("username")
            password = kwargs.get("password")
            if not username or not password:
                raise ValueError(
                    "Missing required keyword arguments: 'username' and/or 'password'"
                )
        else:
            secrets = AccountLogin.load_secrets()
            username, password = secrets.get("username"), secrets.get("password")

        self.username, self.password = username, password
        self.session = None  # in case of use of requests or similar libraries
        self.cookies_file = None

    @staticmethod
    def load_secrets(path_to_secrets: str = config.SECRETS_FILE) -> Dict[str, Any]:
        """
        Load configuration from a YAML file.
        Args:
            path_to_secrets (str): Path to the YAML configuration file.

        Returns:
            Dict[str, Any]: Configuration as a dictionary.

        Raises:
            FileNotFoundError: If the configuration file is not found.
            ValueError: If the YAML file has invalid syntax.
        """
        logger.info(f"Loading configuration from: {path_to_secrets}")
        try:
            with open(path_to_secrets, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if not isinstance(config, dict):
                raise ValueError(
                    "Configuration file must contain a dictionary at the top level."
                )
            return config
        except FileNotFoundError as e:
            logger.error(f"Configuration file '{path_to_secrets}' not found.")
            raise
        except yaml.YAMLError as e:
            logger.error(
                f"Invalid YAML format in configuration file '{path_to_secrets}': {e}"
            )
            raise

    def set_cookies_file(self, cookies_file: str) -> None:
        """
        Set the path to the cookies file.
        Args:
            cookies_file (str): Path to the cookies file.
        """
        self.cookies_file = cookies_file
        logger.info(f"Cookies file set to: {self.cookies_file}")

    @abstractmethod
    def perform_login(self, login_webpage: str):
        """
        Create a session and login to the account.
        This method should be implemented in subclasses to handle specific login mechanisms.
        Args:
            login_webpage (str): Authentication page URL.
        """
        pass

    @abstractmethod
    def get_cookies(self) -> Dict[str, str]:
        """
        Retrieve the cookies after a successful login.
        This method should be implemented in subclasses to return the session cookies.
        Returns:
            Dict[str, str]: Cookies as a dictionary.
        """
        pass

class CarrefourAccountLogin(AccountLogin):
    """
    A class to handle Carrefour account login operations.
    This class extends the AccountLogin abstract base class.
    """

    def perform_login(self, login_webpage: str) -> None:
        """
        Perform login to the Carrefour account using curl and save cookies to a file.
        Args:
            login_webpage (str): Authentication page URL.
        """
        if self.cookies_file:
            logger.info(f"Logging in to Carrefour account at {login_webpage}...")
            # store cookies in cookies.txt file after authentication
            curl_command = [
                "curl",
                "-c",
                self.cookies_file,
                "-d",
                f"username={self.username}&password={self.password}",
                "-X",
                "POST",
                login_webpage,
            ]
            try:
                subprocess.run(curl_command, check=True)
                logger.info("Login successful. Cookies saved.")
            except subprocess.CalledProcessError as e:
                logger.error(f"Login failed: {e}")
                raise
        else:
            logger.error(
                "Cookies file path is not set. Please set it using set_cookies_file method."
            )
            raise ValueError("Cookies file path is not set.")

    def get_cookies(self) -> Dict[str, str]:
        """
        Retrieve the cookies after a successful login.
        Returns:
            Dict[str, str]: Cookies as a dictionary.
        """
        if not Path(COOKIES_FILE).exists():
            raise FileNotFoundError("Cookies file not found. Please log in first.")
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            cookies = {}
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 7:  # Ensure there are enough parts for a valid cookie
                    cookies[parts[5]] = unquote(parts[6])  # Decode the cookie value
        return cookies
