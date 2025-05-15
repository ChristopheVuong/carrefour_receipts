# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
import csv
from datetime import datetime
import json
import logging
from typing import Dict, List, Any
import subprocess
from pathlib import Path
from urllib.parse import urlencode, unquote

import yaml

# Configure logging (logging to console or in log file)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Define constants
MAX_SCROLLS = 5  # Maximum number of scrolls to fetch data


class AccountAPIHandler(ABC):
    """
    Abstract wrapper base class for handling account API interactions (retail store online or physical).
    """

    def __init__(
        self, cookies_file: str = "cookies.txt", dst_folder: str = "data/"
    ) -> None:
        """
        Initialize the handler with default configurations.
        Args:
            cookies_file (str): Path to the cookies file.
            dst_folder (str): Folder to save fetched data.
        """
        self.cookies_file = cookies_file
        self.dst_folder = dst_folder
        AccountAPIHandler.ensure_directory_exists(self.dst_folder)

    @staticmethod
    def ensure_directory_exists(folder: str) -> None:
        """
        Ensure the destination directory exists. If not, create it.
        Args:
            folder (str): Path to the folder.
        """
        folder_path = Path(folder)
        if not folder_path.exists():
            folder_path.mkdir(parents=True)
            logger.info(f"Created directory: {folder}")

    @abstractmethod
    def perform_login(self, login_webpage: str, *args, **kwargs) -> None:
        """
        Perform login to the account.
        Args:
            login_webpage (str): Authentication page URL.
            *args: Positional arguments for credentials.
            **kwargs: Keyword arguments for credentials.
        """
        pass

    @staticmethod
    def load_secrets(path_to_secrets: str = "secrets.yml") -> Dict[str, Any]:
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

    @abstractmethod
    def fetch_data(
        self,
        url: str,
        params: Dict[str, Any],
        referer: str,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch data from the API.
        Args:
            url (str): API endpoint URL.
            params (Dict[str, Any]): Query parameters for the API.
            referer (str): Indicates the referer for a more human curl command.
            verbose (bool): Whether to print detailed logs.
        Returns:
            Dict[str, Any]: Parsed JSON response.
        """
        pass

    @abstractmethod
    def fetch_receipt_details(
        self, base_url: str, refs: Dict[str, Any], verbose: bool = False
    ) -> None:
        """
        Fetch detailed receipt data (physical purchase) from the API and write it to json file.
        Args:
            base_url (str): API endpoint URL.
            refs (Dict[str, Any]): Receipt references.
            verbose (bool): Whether to print detailed logs.
        """
        pass

    @abstractmethod
    def fetch_order_details(
        self, base_url: str, refs: Dict[str, Any], verbose: bool = False
    ) -> None:
        """
        Fetch detailed order data (online purchase) from the API and write it to json file.
        Args:
            base_url (str): API endpoint URL.
            refs (Dict[str, Any]): Order references.
            verbose (bool): Whether to print detailed logs.
        """
        pass

    def save_data_to_file(self, data: Dict[str, Any], filename: str) -> None:
        """
        Save data to a JSON file in the destination folder.
        Args:
            data (Dict[str, Any]): Data to save.
            filename (str): Name of the file.
        """
        date_str = datetime.now().strftime("%Y%m%d")
        filepath = Path(self.dst_folder) / date_str / filename
        if not filepath.parent.exists():
            filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        logger.info(f"Data saved to: {self.dst_folder}{filename}")

    @staticmethod
    def check_params(params: Dict[str, Any], required_params: List[str]):
        for param in required_params:
            if param not in params:
                raise ValueError(f"Missing required parameter: {param}")
        logger.info("All required parameters are present.")


class CarrefourAccountAPIHandler(AccountAPIHandler):
    """
    A wrapper class to handle login, fetching data from an API, and saving it locally.
    """

    BRAND_NAME = "carrefour"
    BRAND_REFERER = {
        "referer_store": "https://www.carrefour.fr/mon-compte/mes-achats/en-magasin",
        "referer_drive": "https://www.carrefour.fr/mon-compte/mes-achats/en-ligne",
        "referer_loyalty": "https://www.carrefour.fr/mon-compte/fidelite/historique",
    }

    def __init__(
        self, cookies_file: str = "cookies.txt", dst_folder: str = "data/"
    ) -> None:
        """
        Initialize the handler with default configurations.
        Args:
            cookies_file (str): Path to the cookies file.
            dst_folder (str): Folder to save fetched data.
        """
        super().__init__(cookies_file=cookies_file, dst_folder=dst_folder)
        # open for extension

    def perform_login(self, login_webpage: str, *args, **kwargs) -> None:
        """
        Perform login using curl and save cookies to a file.
        Supports multiple input formats for credentials.
        Args:
            login_webpage (str): Authentication page URL.
            *args: Positional arguments (e.g., a dictionary for user_id).
            **kwargs: Keyword arguments (e.g., username and password).
        Raises:
            ValueError: If no valid input is provided.
            KeyError: If required keys are missing in the dictionary.
            subprocess.CalledProcessError: If the curl command fails.
        Note: This method does not bypass Cloudfare turnstile anti-bot protection.
        The same goes for Selenium, Playwright (cf_waiting_room remain). Use a browser instead.
        """
        try:
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
                secrets = CarrefourAccountAPIHandler.load_secrets()
                username, password = secrets.get("username"), secrets.get("password")
            if username and password:
                logger.info(f"Logging in with username: {username}")
                CarrefourAccountAPIHandler.login_with_curl(
                    login_webpage, username, password, self.cookies_file
                )
            else:
                logger.warning("Username or password is missing.")
                return

        except subprocess.CalledProcessError as e:
            logger.error(f"Login failed: {e}")
            raise

    @staticmethod
    def login_with_curl(
        login_webpage: str, username: str, password: str, cookies_file: str
    ) -> None:
        """
        Perform login using curl and save cookies to a file.
        """
        login_payload = f"idToken1={username}&idToken2={password}"
        subprocess.run(
            [
                "curl",
                "-c",
                cookies_file,
                "-d",
                login_payload,
                "-H",
                "Content-Type: application/x-www-form-urlencoded",
                "-X",
                "POST",
                login_webpage,
            ],
            check=True,
        )
        logger.info(f"Login successful. Cookies saved to {cookies_file}")

    def fetch_paginated_receipts(
        self,
        url: str,
        params: Dict[str, Any],
        max_scrolls: int = MAX_SCROLLS,
        verbose: bool = False,
    ) -> None:
        """
        Fetch paginated data from the API and save it locally.
        Args:
            url (str): API endpoint URL.
            params (Dict[str, Any]): Initial query parameters.
            max_scrolls (int): Maximum number of pagination requests.
            verbose (bool): Whether to print detailed logs.
        """
        CarrefourAccountAPIHandler.check_loyalty_params(params)
        date_time_str = datetime.now().strftime("%Y%m%d_%H_%M")
        loyalty_card_number = params.get("loyaltyCardNumber", "unknown")

        # Fetch initial data
        logger.info("Fetching initial data...")
        data = self.fetch_data(
            url,
            params,
            referer=CarrefourAccountAPIHandler.BRAND_REFERER.get("referer_store", ""),
            verbose=verbose,
        )
        self.save_data_to_file(
            data,
            f"{date_time_str}-{loyalty_card_number}_{CarrefourAccountAPIHandler.BRAND_NAME}_receipts_scroll_0.json",
        )

        # Fetch subsequent pages
        for scroll in range(1, max_scrolls + 1):
            logger.info(f"Fetching data for scroll: {scroll}")
            try:
                params["scrollPaging"] = data["meta"].get("scrollPaging", "")
                params["scrollHash"] = data["meta"].get("scrollHash", "")
                data = self.fetch_data(
                    url,
                    params,
                    referer=CarrefourAccountAPIHandler.BRAND_REFERER.get(
                        "referer_store", ""
                    ),
                    verbose=verbose,
                )
                if not data:
                    logger.info("No more data to fetch.")
                    break
                self.save_data_to_file(
                    data,
                    f"{date_time_str}-{loyalty_card_number}_{CarrefourAccountAPIHandler.BRAND_NAME}_receipts_scroll_{scroll}.json",
                )
            except Exception as e:
                logger.error(f"Error during data fetching: {e}")
                break

    def fetch_all_receipts(
        self, url: str, params: Dict[str, Any], verbose: bool = False
    ) -> None:
        """
        Fetch all paginated data from the API and save it locally.
        Args:
            url (str): API endpoint URL.
            params (Dict[str, Any]): Initial query parameters.
            verbose (bool): Whether to print detailed logs.
        """
        CarrefourAccountAPIHandler.check_loyalty_params(params)
        date_time_str = datetime.now().strftime("%Y%m%d_%H_%M")
        loyalty_card_number = params.get("loyaltyCardNumber", "unknown")

        # Fetch initial data
        logger.info("Fetching initial data...")
        data = self.fetch_data(
            url,
            params,
            referer=CarrefourAccountAPIHandler.BRAND_REFERER.get("referer_store", ""),
            verbose=verbose,
        )
        self.save_data_to_file(
            data,
            f"{date_time_str}-{loyalty_card_number}_{CarrefourAccountAPIHandler.BRAND_NAME}_receipts_all_scroll_0.json",
        )

        # Fetch all subsequent pages
        scroll = 1
        while data.get("meta", {}).get("scrollHash"):
            logger.info(f"Fetching data for scroll: {scroll}")
            try:
                params["scrollPaging"] = data["meta"].get("scrollPaging", "")
                params["scrollHash"] = data["meta"].get("scrollHash", "")
                data = self.fetch_data(
                    url,
                    params,
                    referer=CarrefourAccountAPIHandler.BRAND_REFERER.get(
                        "referer_store", ""
                    ),
                    verbose=verbose,
                )
                if not data:
                    logger.info("No more data to fetch.")
                    break
                self.save_data_to_file(
                    data,
                    f"{date_time_str}-{loyalty_card_number}_{CarrefourAccountAPIHandler.BRAND_NAME}_receipts_all_scroll_{scroll}.json",
                )
                scroll += 1
            except Exception as e:
                logger.error(f"Error during data fetching: {e}")
                break

    def fetch_all_orders(
        self, url: str, params: Dict[str, Any], verbose: bool = False
    ) -> None:
        """
        Fetch all paginated data from the API and save it locally.
        Args:
            url (str): API endpoint URL.
            params (Dict[str, Any]): Initial query parameters.
            verbose (bool): Whether to print detailed logs.
        """
        CarrefourAccountAPIHandler.check_order_params(params)
        date_time_str = datetime.now().strftime("%Y%m%d_%H_%M")

        # Fetch initial data
        start_date = params.get("startDate", "unknownDate")[:10]
        logger.info("Fetching initial data...")
        data = self.fetch_data(
            url,
            params,
            referer=CarrefourAccountAPIHandler.BRAND_REFERER.get("referer_drive", ""),
            verbose=verbose,
        )
        self.save_data_to_file(
            data,
            f"{date_time_str}-{start_date}_{CarrefourAccountAPIHandler.BRAND_NAME}_orders_all_scroll_0.json",
        )

        # Fetch all subsequent pages
        scroll = 1
        while data.get("meta", {}).get("scrollHash"):
            logger.info(f"Fetching data for scroll: {scroll}")
            try:
                params["scrollPaging"] = data["meta"].get("scrollPaging", "")
                params["scrollHash"] = data["meta"].get("scrollHash", "")
                data = self.fetch_data(
                    url,
                    params,
                    referer=CarrefourAccountAPIHandler.BRAND_REFERER.get(
                        "referer_drive", ""
                    ),
                    verbose=verbose,
                )
                if not data:
                    logger.info("No more data to fetch.")
                    break
                self.save_data_to_file(
                    data,
                    f"{date_time_str}-{start_date}_{CarrefourAccountAPIHandler.BRAND_NAME}_orders_all_scroll_{scroll}.json",
                )
                scroll += 1
            except Exception as e:
                logger.error(f"Error during data fetching: {e}")
                break

    def fetch_all_loyalty(
        self, url: str, params: Dict[str, Any], verbose: bool = False
    ) -> None:
        """
        Fetch all the loyalty details given a reference date in params.
        Args:
            url (str): API endpoint URL.
            params (Dict[str, Any]): Initial query parameters.
            verbose (bool): Whether to print detailed logs.
        """
        CarrefourAccountAPIHandler.check_loyalty_transactions_params(params)
        end_date = datetime.now()
        date_time_str = end_date.strftime("%Y%m%d_%H_%M")
        date = params.get("date")
        if not date:
            raise ValueError("The date is None.")
        month = int(date[:2])
        year = int(date[-4:])
        logger.info("Fetching initial data...")
        # TODO: to continue with loop over dates
        try:
            current_date = datetime(
                year=year, month=month, day=1
            )  # Start with the initial date
            end_date_obj = datetime(
                year=end_date.year, month=end_date.month, day=1
            )  # Normalize end_date to the first day of the month

            while current_date < end_date_obj:
                # Format the date as "MM/01/YYYY"
                params["date"] = current_date.strftime(
                    "%m/01/%Y"
                )  # Use strftime for consistent formatting [[10]]

                # Fetch data
                data = self.fetch_data(
                    url,
                    params,
                    referer=CarrefourAccountAPIHandler.BRAND_REFERER.get(
                        "referer_loyalty", ""
                    ),
                    verbose=verbose,
                )

                if not data:
                    logger.info("No data to fetch.")
                    current_date = self._increment_month(
                        current_date
                    )  # Increment the date
                    continue

                # Process history data
                if "history" in data and not data["history"]:
                    current_date = self._increment_month(
                        current_date
                    )  # Increment the date
                    continue

                # Save the data to a file
                formatted_date = current_date.strftime("%m-%d-%Y").replace("/", "-")
                self.save_data_to_file(
                    data,
                    f"{date_time_str}-{formatted_date}_{CarrefourAccountAPIHandler.BRAND_NAME}_loyalty_transactions_all.json",
                )

                # Move to the next month
                current_date = self._increment_month(current_date)

        except Exception as e:
            logger.error(f"Error during data fetching: {e}")

    def _increment_month(self, current_date: datetime):
        """
        Increment the month, rolling over to the next year if necessary
        """
        if current_date.month == 12:
            return current_date.replace(year=current_date.year + 1, month=1)
        return current_date.replace(month=current_date.month + 1)

    def fetch_data(
        self,
        url: str,
        params: Dict[str, Any],
        referer: str = "",
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch data from the hidden API URL using saved cookies and parse JSON.
        Args:
            url (str): API endpoint URL.
            params (Dict[str, Any]): Query parameters for the API.
            is_online (bool): Indicates if the purchase is online or in store.
            verbose (bool): Whether to print detailed logs.
        Returns:
            Dict[str, Any]: Parsed JSON response.
        Raises:
            FileNotFoundError: If the cookies file is not found.
            json.JSONDecodeError: If the response cannot be parsed as JSON.
            subprocess.CalledProcessError: If the curl command fails.
        """
        # cannot use empty string as a parameter
        if "" in params.values():
            return {}
        if not Path(self.cookies_file).exists():
            raise FileNotFoundError("Cookies file not found. Please log in first.")

        api_url = f"{url}?{urlencode(params)}" if params else url

        logger.info(f"Fetching data from: {api_url}")
        curl_command = [
            "curl",
            "-X",
            "GET",
            api_url,
            "-H",
            "accept: application/json, text/plain, */*",
            "-H",
            "accept-language: fr,fr-FR;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "-b",
            self.cookies_file,
            "-H",
            "dnt: 1",
            "-H",
            "priority: u=1, i",
            "-H",
            f"referer: {referer}",
            "-H",
            'sec-ch-ua: "Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "-H",
            "sec-ch-ua-mobile: ?0",
            "-H",
            'sec-ch-ua-platform: "macOS"',
            "-H",
            "sec-fetch-dest: empty",
            "-H",
            "sec-fetch-mode: cors",
            "-H",
            "sec-fetch-site: same-origin",
            "-H",
            "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
            "-H",
            "x-requested-with: XMLHttpRequest",
        ]
        try:
            # realistic request headers
            result = subprocess.run(
                curl_command,
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            logger.info("Parsed JSON Data:")
            if verbose:
                print(json.dumps(data, indent=4))
            return data
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fetch API data: {e}")
            raise

    def extract_receipts_ids(
        self,
        criterion1: str = "carrefour_receipt_",
        criterion2: str = "",
        output_file: str = "data/receipts_ids.csv",
    ) -> None:
        """
        Extract receipt IDs from the fetched data in dst_folder.
        Args:
            criterion1 (str): Name criterion for JSON files.
            criterion2 (str): Additional criterion for filtering files by batch (the extraction date by default).
            output_file (str): Path to the output CSV file.
        """
        rows = []
        headers = CarrefourAccountAPIHandler.get_receipt_list_headers()
        headers.append("dateExtraction")
        for file in Path(self.dst_folder).rglob(f"{criterion2}*{criterion1}*.json"):
            with open(file, "r", encoding="utf-8") as f:
                item = json.load(f)
                if "data" in item:
                    for receipt in item["data"]:
                        rows.append(
                            [
                                receipt.get(headers[0]),
                                receipt.get("attributes").get(headers[1]),
                                receipt.get("attributes").get(headers[2]),
                                receipt.get("attributes").get(headers[3]),
                                criterion2,  # a criterion by default the extraction date
                            ]
                        )
        logger.info(f"Extracted {len(rows)} receipt IDs.")
        if rows:
            # Open a file or write it if it doesn't exist
            file_exists = Path(output_file).exists()
            with open(output_file, "a+", newline="\n", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(headers)
                writer.writerows(rows)
            logger.info(f"Receipt IDs saved to: {output_file}")
        else:
            logger.warning("No receipt IDs found.")

    def extract_orders_ids(
        self,
        criterion1: str = "carrefour_order_",
        criterion2: str = "",
        output_file: str = "data/orders_ids.csv",
    ) -> None:
        """
        Extract order IDs from the fetched data in dst_folder.
        Args:
            criterion1 (str): Name criterion for JSON files.
            criterion2 (str): Additional criterion for filtering files by batch (the extraction date by default).
            output_file (str): Path to the output CSV file.
        """
        rows = []
        headers = CarrefourAccountAPIHandler.get_order_list_headers()
        headers.append("dateExtraction")
        # Extract order IDs from JSON files
        for file in Path(self.dst_folder).rglob(f"{criterion2}*{criterion1}*.json"):
            with open(file, "r", encoding="utf-8") as f:
                item = json.load(f)
                if "data" in item:
                    for order in item["data"]:
                        rows.append(
                            [
                                order.get("attributes").get(headers[0]),
                                criterion2,  # a criterion by default the extraction date
                            ]
                        )
        logger.info(f"Extracted {len(rows)} order IDs.")
        if rows:
            # Open a file or write it if it doesn't exist
            file_exists = Path(output_file).exists()
            # newline = "" or "\n" to avoid blank lines in CSV
            with open(output_file, "a+", newline="\n", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(headers)
                writer.writerows(rows)
            logger.info(f"Order IDs saved to: {output_file}")
        else:
            logger.warning("No order IDs found.")

    def extract_loyalty_details(
        self,
        criterion1: str = "carrefour_loyalty_",
        criterion2: str = "",
        output_file: str = "data/loyalty_ids.csv",
    ) -> None:
        """
        Extract order IDs from the fetched data in dst_folder.
        Args:
            criterion1 (str): Name criterion for JSON files.
            criterion2 (str): Additional criterion for filtering files by batch (the extraction date by default).
            output_file (str): Path to the output CSV file.
        """
        rows = []
        headers = CarrefourAccountAPIHandler.get_loyalty_list_headers()
        headers.append("dateExtraction")
        # Extract order IDs from JSON files
        for file in Path(self.dst_folder).rglob(f"{criterion2}*{criterion1}*.json"):
            with open(file, "r", encoding="utf-8") as f:
                item = json.load(f)
                if "history" in item:
                    for op in item["history"]:
                        rows.append(
                            [
                                op.get(headers[0]),
                                criterion2,  # a criterion by default the extraction date
                            ]
                        )
        logger.info(f"Extracted {len(rows)} order IDs.")
        if rows:
            # Open a file or write it if it doesn't exist
            file_exists = Path(output_file).exists()
            # newline = "" or "\n" to avoid blank lines in CSV
            with open(output_file, "a+", newline="\n", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(headers)
                writer.writerows(rows)
            logger.info(f"Loyalty transaction IDs saved to: {output_file}")
        else:
            logger.warning("No loyalty transactions IDs found.")

    def fetch_receipt_details(
        self, base_url: str, refs: Dict[str, Any], verbose: bool = False
    ) -> None:
        """
        Fetch detailed receipt data from the API.
        Args:
            base_url (str): API endpoint URL.
            refs (Dict[str, Any]): Receipt references.
            verbose (bool): Whether to print detailed logs.
        """
        date_time_str = datetime.now().strftime("%Y%m%d_%H_%M")
        CarrefourAccountAPIHandler.check_receipt_refs(refs)
        headers = CarrefourAccountAPIHandler.get_receipt_list_headers()
        url = f"{base_url}/{refs[headers[1]]}/{refs[headers[2]]}/{refs[headers[3]]}"
        data = self.fetch_data(
            url,
            params={},
            referer=CarrefourAccountAPIHandler.BRAND_REFERER.get("referer_store", ""),
            verbose=verbose,
        )
        self.save_data_to_file(
            data,
            f"{date_time_str}-{CarrefourAccountAPIHandler.BRAND_NAME}_receipt_{refs[headers[0]]}_details.json",
        )

    def fetch_order_details(
        self, base_url: str, refs: Dict[str, Any], verbose: bool = False
    ) -> None:
        """
        Fetch detailed order data from the API.
        Args:
            base_url (str): API endpoint URL.
            refs (Dict[str, Any]): Order references.
            verbose (bool): Whether to print detailed logs.
        """
        date_time_str = datetime.now().strftime("%Y%m%d_%H_%M")
        CarrefourAccountAPIHandler.check_order_refs(refs)
        headers = CarrefourAccountAPIHandler.get_order_list_headers()
        url = f"{base_url}/{refs[headers[0]]}"
        data = self.fetch_data(
            url,
            params={},
            referer=CarrefourAccountAPIHandler.BRAND_REFERER.get("referer_drive", ""),
            verbose=verbose,
        )
        self.save_data_to_file(
            data,
            f"{date_time_str}-{CarrefourAccountAPIHandler.BRAND_NAME}_order_{refs[headers[0]]}_details.json",
        )

    def fetch_loyalty_details(
        self, base_url: str, refs: Dict[str, Any], verbose: bool = False
    ) -> None:
        """
        Fetch detailed loyalty data from the API.
        Args:
            base_url (str): API endpoint URL.
            refs (Dict[str, Any]): loyalty references.
            verbose (bool): Whether to print detailed logs.
        """
        date_time_str = datetime.now().strftime("%Y%m%d_%H_%M")
        CarrefourAccountAPIHandler.check_loyalty_refs(refs)
        headers = CarrefourAccountAPIHandler.get_loyalty_list_headers()
        url = f"{base_url}/{refs[headers[0]]}"
        data = self.fetch_data(
            url,
            params={},
            referer=CarrefourAccountAPIHandler.BRAND_REFERER.get("referer_loyalty", ""),
            verbose=verbose,
        )
        data["operationId"] = refs[headers[0]]
        self.save_data_to_file(
            data,
            f"{date_time_str}-{CarrefourAccountAPIHandler.BRAND_NAME}_loyalty_operation_{refs[headers[0]]}_details.json",
        )

    @staticmethod
    def remove_duplicates_from_list(file_path: str) -> None:
        """
        Remove duplicate rows from a CSV file in place based on the first column.
        Args:
            file_path (str): Path to the CSV file.
        """
        seen = set()
        unique_rows = []

        # Read the file and filter out duplicates
        with open(file_path, "r", encoding="utf-8") as infile:
            reader = csv.reader(infile)
            for row in reader:
                if row[0] not in seen:  # Check if the first column value is unique
                    seen.add(row[0])  # _id or id column
                    unique_rows.append(row)

        if unique_rows:
            # Overwrite the file with the unique rows
            with open(file_path, "w", encoding="utf-8") as outfile:
                writer = csv.writer(outfile)
                writer.writerows(unique_rows)

        logger.info(f"Duplicates removed in place. File updated: {file_path}")

    def fetch_details_from_file(
        self,
        base_url: str,
        input_file: str,
        criterion: str = datetime.now().strftime("%Y%m%d"),
        type: str = "receipt",
        verbose: bool = False,
    ) -> None:
        """
        Fetch detailed receipt data from the API using IDs from a CSV file.
        Args:
            base_url (str): API endpoint URL.
            input_file (str): Path to the CSV file with receipt IDs.
            criterion (str): Criterion based on which receipts are fetched.
            is_online (bool): Whether to fetch data from online purchases or in-store.
            verbose (bool): Whether to print detailed logs.
        """
        match type:
            case "receipt":
                headers = self.get_order_list_headers()
            case "order":
                headers = self.get_receipt_list_headers()
            case "loyalty":
                headers = self.get_loyalty_list_headers()
            case _:
                raise ValueError(
                    "The type should be either 'receipt', 'order' or 'loyalty'."
                )
        with open(input_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # criterion based on date
                if row.get("dateExtraction") != criterion:
                    continue
                # criterion based on id
                if not row.get(headers[0]):
                    continue
                match type:
                    case "receipt":
                        self.fetch_receipt_details(base_url, row, verbose=verbose)
                    case "order":
                        self.fetch_order_details(base_url, row, verbose=verbose)
                    case "loyalty":
                        self.fetch_loyalty_details(base_url, row, verbose=verbose)
                    case _:
                        self.fetch_receipt_details(base_url, row, verbose=verbose)

    @staticmethod
    def check_loyalty_params(params: Dict[str, Any]) -> None:
        """
        Validate required parameters.
        Args:
            params (Dict[str, Any]): Parameters to validate.
        Raises:
            ValueError: If any required parameter is missing.
        """
        required_params = ["loyaltyCardNumber", "loyaltyCardType"]
        AccountAPIHandler.check_params(params, required_params)

    @staticmethod
    def check_order_params(params: Dict[str, Any]) -> None:
        """
        Validate required parameters.
        Args:
            params (Dict[str, Any]): Parameters to validate.
        Raises:
            ValueError: If any required parameter is missing.
        """
        required_params = ["startDate", "endDate"]
        AccountAPIHandler.check_params(params, required_params)

    @staticmethod
    def check_loyalty_transactions_params(params: Dict[str, Any]) -> None:
        """
        Validate required parameters.
        Args:
            params (Dict[str, Any]): Parameters to validate.
        Raises:
            ValueError: If any required parameter is missing.
        """
        required_params = ["date"]
        AccountAPIHandler.check_params(params, required_params)

    @staticmethod
    def check_receipt_refs(params: Dict[str, Any]) -> None:
        """
        Validate required parameters.
        Args:
            params (Dict[str, Any]): Parameters to validate.
        Raises:
            ValueError: If any required parameter is missing.
        """
        required_params = ["gln", "dateKey", "receiptNumber"]
        AccountAPIHandler.check_params(params, required_params)

    @staticmethod
    def check_order_refs(params: Dict[str, Any]) -> None:
        """
        Validate required parameters.
        Args:
            params (Dict[str, Any]): Parameters to validate.
        Raises:
            ValueError: If any required parameter is missing.
        """
        required_params = ["orderNumber"]
        AccountAPIHandler.check_params(params, required_params)

    @staticmethod
    def check_loyalty_refs(params: Dict[str, Any]) -> None:
        """
        Validate required parameters.
        Args:
            params (Dict[str, Any]): Parameters to validate.
        Raises:
            ValueError: If any required parameter is missing.
        """
        required_params = ["operationId"]
        AccountAPIHandler.check_params(params, required_params)

    @staticmethod
    def get_receipt_list_headers() -> List[str]:
        """
        Get headers for the receipt list.
        Returns:
            Dict[str, Any]: Headers for the receipt list.
        """
        return ["id", "gln", "dateKey", "receiptNumber"]

    @staticmethod
    def get_order_list_headers() -> List[str]:
        """
        Get headers for the receipt list.
        Returns:
            Dict[str, Any]: Headers for the receipt list.
        """
        return ["orderNumber"]

    @staticmethod
    def get_loyalty_list_headers() -> List[str]:
        """
        Get headers for the receipt list.
        Returns:
            Dict[str, Any]: Headers for the receipt list.
        """
        return ["operationId"]


def main_store():
    """
    Extract the details from store receipts according to some criterions (automated or not)
    """
    api_url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
    api_details_url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipt"
    cookies_file = "cookies.txt"
    config = CarrefourAccountAPIHandler.load_secrets()
    params_loyalty = {
        "loyaltyCardNumber": config.get("loyaltyCardNumber"),
        "loyaltyCardType": "LOYALTY",
    }

    params_pass = {
        "loyaltyCardNumber": config.get("passCardNumber"),
        "loyaltyCardType": "PASS_MASTERCARD",
    }

    # Initialize the handler
    handler = CarrefourAccountAPIHandler(cookies_file=cookies_file)

    # # Step 1: Perform login
    # handler.perform_login("https://www.carrefour.fr/login")

    # Step 2: Fetch paginated data or whole data
    # handler.fetch_paginated_receipts(api_url, params_loyalty, max_scrolls=0, verbose=True)
    handler.fetch_all_receipts(api_url, params_pass, verbose=False)

    # Step 3: Extract receipt IDs
    handler.extract_receipts_ids(
        criterion1=f"{CarrefourAccountAPIHandler.BRAND_NAME}_receipts_",
        criterion2=datetime.now().strftime("%Y%m%d"),
        output_file="data/receipts_ids.csv",
    )
    CarrefourAccountAPIHandler.remove_duplicates_from_list("data/receipts_ids.csv")

    # Step 4: Fetch receipt details
    handler.fetch_details_from_file(
        base_url=api_details_url,
        input_file="data/receipts_ids.csv",
        criterion=datetime.now().strftime("%Y%m%d"),
        type="receipt",
        verbose=False,
    )


def main_drive():
    """
    Extract the details from Drive orders according to some criterions
    Note: It may also extract CLICK AND COLLECT items
    """
    api_url = "https://www.carrefour.fr/api/user/orders"
    api_details_url = "https://www.carrefour.fr/api/user/orders"
    cookies_file = "cookies.txt"
    end_date = datetime.now().strftime("%Y-%m-%d")  # YYYY-MM-DD
    # datetime string format: use unquote to decode URL-encoded string
    params_drive = {
        "startDate": unquote(
            "2022-01-01T00%3A00%3A00.000Z"
        ),  # peculiar filter in carrefour.fr
        "endDate": unquote(f"{end_date}T00%3A00%3A00.000Z"),
    }

    # Initialize the handler
    handler = CarrefourAccountAPIHandler(cookies_file=cookies_file)

    # # # Step 1: Perform login
    # # handler.perform_login("https://www.carrefour.fr/login")

    # Step 2: Fetch paginated data or whole data
    handler.fetch_all_orders(api_url, params_drive, verbose=False)
    # handler.fetch_all_receipts(api_url, params_pass, verbose=False)

    # Step 3: Extract order IDs
    handler.extract_orders_ids(
        criterion1=f"{CarrefourAccountAPIHandler.BRAND_NAME}_orders_",
        criterion2=datetime.now().strftime("%Y%m%d"),
        output_file="data/orders_ids.csv",
    )
    CarrefourAccountAPIHandler.remove_duplicates_from_list("data/orders_ids.csv")

    # Step 4: Fetch receipt details
    handler.fetch_details_from_file(
        base_url=api_details_url,
        input_file="data/orders_ids.csv",
        criterion=datetime.now().strftime("%Y%m%d"),
        type="order",
        verbose=False,
    )


def main_loyalty():
    """
    Extract loyalty history and loyalty operations in order to feed loyalty and loyaltyOperations collections in Carrefour database
    """
    api_url = "https://www.carrefour.fr/api/user/secured/loyalty/transactions"
    api_details_url = "https://www.carrefour.fr/api/user/secured/loyalty/transactions"
    cookies_file = "cookies.txt"

    params = {"date": "04/01/2022"}
    # Initialize the handler
    handler = CarrefourAccountAPIHandler(cookies_file=cookies_file)
    handler.fetch_all_loyalty(api_url, params)
    handler.extract_loyalty_details(
        criterion1=f"{CarrefourAccountAPIHandler.BRAND_NAME}_loyalty_transactions",
        criterion2="20250506",
        output_file="data/loyalty_ids.csv",
    )
    # Step 4: Fetch receipt details
    handler.fetch_details_from_file(
        base_url=api_details_url,
        input_file="data/loyalty_ids.csv",
        criterion="20250506",
        type="loyalty",
        verbose=False,
    )


def main(script_name: str = "store"):
    match script_name:
        case "store":
            main_store()
        case "drive":
            main_drive()
        case "loyalty":
            main_loyalty()
        case _:
            logger.warning(
                "Please choose between script_name: 'store', 'drive' or 'loyalty'."
            )


# Main execution
if __name__ == "__main__":
    main("store")
