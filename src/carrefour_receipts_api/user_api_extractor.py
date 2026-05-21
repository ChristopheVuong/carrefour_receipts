# -*- coding: utf-8 -*-
"""
TODO: Try batch call API with receipt refs
"""

from abc import ABC, abstractmethod
import csv
from datetime import datetime
import json
from typing import Any
import subprocess
from pathlib import Path
from urllib.parse import urlencode, unquote

from carrefour_receipts_api.login import AccountLogin
from carrefour_receipts_api.logging_config import get_logger
from carrefour_receipts_api.utils import check_keys, unpack_dict_zip

# Structured logging (console or JSON via LOG_JSON) — see logging_config.
logger = get_logger(__name__)

# Define constants (e.g. number of fetching iterations and personal data folder)
MAX_SCROLLS = float("inf")  # Maximum number of scrolls to fetch data
DATA_DIRECTORY = "data"  # Directory to save fetched data (relative to the current directory by default the root of the project)
COOKIES_FILE = f"{DATA_DIRECTORY}/cookies.txt"  # Path to the cookies file (relative to the current directory by default the root of the project)


class BaseExtractor(ABC):
    """
    Abstract wrapper base class for handling account API interactions (retail store online or physical).
    """

    PARAM_KEYS = []

    def __init__(self, auth: str, dst_folder: str = DATA_DIRECTORY) -> None:
        """
        Initialize the extractor with default configurations.
        Args:
            auth (str): authentication token or some password.
            dst_folder (str): Folder to save fetched data.
        """
        self.auth = auth
        self.dst_folder = dst_folder
        BaseExtractor.ensure_directory_exists(self.dst_folder)

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
    def fetch_data(
        self,
        url: str,
        params: dict[str, Any],
        referer: str,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Fetch data from the API.

        Args:
            url (str): API endpoint URL.
            params (Dict[str, Any]): Query parameters for the API.
            referer (str): Indicates the referer for a more human curl command.
            verbose (bool): Whether to print detailed logs.

        Returns:
            Dict[str, Any]: Parsed JSON response from the API.
        """
        pass

    @abstractmethod
    def fetch_details(
        self, base_url: str, refs: dict[str, Any], verbose: bool = False
    ) -> None:
        """
        Fetch detailed data (either receipts, orders, or loyalty data) from the API and write it to json file.
        Args:
            base_url (str): API endpoint URL.
            refs (Dict[str, Any]): Receipt references.
            verbose (bool): Whether to print detailed logs.
        """
        pass

    def save_data_to_file(self, data: dict[str, Any], filename: str) -> None:
        """
        Save data to a JSON file in the destination folder.
        Args:
            data (Dict[str, Any]): Data to save.
            filename (str): Name of the file.
        """
        if data:
            date_str = datetime.now().strftime("%Y%m%d")
            filepath = Path(self.dst_folder) / date_str / filename
            if not filepath.parent.exists():
                filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(
                json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
            )
            logger.info(f"Data saved to: {self.dst_folder}/{filename}")

    @classmethod
    def check_params(cls, params: dict[str, Any]):
        for param in cls.PARAM_KEYS:
            if param not in params:
                raise ValueError(f"Missing required parameter: {param}")
        logger.info("All required parameters are present.")


class CarrefourBaseExtractor(BaseExtractor):
    """
    Base extractor for Carrefour-related data extraction.
    Provides shared functionality for different types of Carrefour data (e.g., receipts, orders, loyalty).
    """

    BRAND_NAME = "carrefour"
    REFERER_URL = ""
    RECORD_TYPE = ""
    PARAM_KEYS = []

    def __init__(
        self, cookies_file: str = COOKIES_FILE, dst_folder: str = DATA_DIRECTORY
    ) -> None:
        """
        Initialize the handler with default configurations.
        Args:
            cookies_file (str): Path to the cookies file.
            dst_folder (str): Folder to save fetched data.
        """
        super().__init__("", dst_folder)
        self.cookies_file = cookies_file

    def fetch_paginated_data(
        self,
        url: str,
        params: dict[str, Any],
        max_scrolls: int = MAX_SCROLLS,
        verbose: bool = False,
    ):
        """
        Fetch paginated data from the API and save it locally.
        Args:
            url (str): API endpoint URL.
            params (Dict[str, Any]): Initial query parameters.
            max_scrolls (int): Maximum number of pagination requests.
            verbose (bool): Whether to print detailed logs.
        """
        self.__class__.check_params(params)
        date_time_str = datetime.now().strftime("%Y%m%d_%H_%M")
        number = params.get(self.__class__.PARAM_KEYS[0], "unknown")
        prefix_name = f"{date_time_str}-{number}_{CarrefourBaseExtractor.BRAND_NAME}_{self.__class__.RECORD_TYPE}s"
        if max_scrolls == float("inf"):
            prefix_name += "_all"
        # Fetch initial data
        logger.info("Fetching initial data...")

        data = self.fetch_data(
            url,
            params,
            referer=self.__class__.REFERER_URL,
            verbose=verbose,
        )
        self.save_data_to_file(
            data,
            f"{prefix_name}_scroll_0.json",
        )
        # Fetch subsequent pages
        scroll = 1
        while data.get("meta", {}).get("scrollHash") and scroll < MAX_SCROLLS:
            logger.info(f"Fetching data for scroll: {scroll}")
            try:
                params["scrollPaging"] = data["meta"].get("scrollPaging", "")
                params["scrollHash"] = data["meta"].get("scrollHash", "")
                data = self.fetch_data(
                    url,
                    params,
                    referer=self.__class__.REFERER_URL,
                    verbose=verbose,
                )
                if not data:
                    logger.info("No more data to fetch.")
                    break
                self.save_data_to_file(
                    data,
                    f"{prefix_name}_scroll_{scroll}.json",
                )
                scroll += 1
            except Exception as e:
                logger.error(f"Error during data fetching: {e}")
                break

    def fetch_data(
        self,
        url: str,
        params: dict[str, Any],
        referer: str = "",
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Fetch data from the hidden API URL using saved cookies and parse JSON.
        Args:
            url (str): API endpoint URL.
            params (Dict[str, Any]): Query parameters for the API.
            referer (str): Indicates the referer link for a more human curl command.
            verbose (bool): Whether to print detailed logs.
        Returns:
            Dict[str, Any]: Parsed JSON response.
        Raises:
            FileNotFoundError: If the cookies file is not found. The fetching cannot continue as long as it is not fixed.
            subprocess.CalledProcessError: If the curl command fails, that will propagate to other fetching operations.
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
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fetch API data: {e}")
            raise
        try:
            data = json.loads(result.stdout)
            if verbose:
                logger.debug("parsed_json_data", data=data)
            if "code" in data and "message" in data:
                logger.error("api_error", code=data["code"], message=data["message"])
                return {}
            if "errors" in data:
                logger.error("api_parameter_error")
                return {}
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {result.stdout}")
            return {}

    def extract_ids(
        self,
        criterion1: str,
        criterion2: str,
        output_file: str,
    ) -> None:
        """
        Extract receipt IDs from the fetched data in dst_folder.
        Args:
            criterion1 (str): Name criterion for JSON files.
            criterion2 (str): Additional criterion for filtering files by batch (the extraction date by default).
            output_file (str): Path to the output CSV file.

        Note: This is a quick workaround to limit the number of insertions in MongoDB.
        """
        rows = []
        headers = self.__class__.get_list_headers()
        headers.append("dateExtraction")
        for file in Path(self.dst_folder).rglob(f"{criterion2}*{criterion1}*.json"):
            with open(file, "r", encoding="utf-8") as f:
                item = json.load(f)
                self.__class__.append_row_data(item, rows, headers, criterion2)
        logger.info(f"Extracted {len(rows)} {self.__class__.RECORD_TYPE} IDs.")
        if rows:
            # Open a file or write it if it doesn't exist
            file_exists = Path(output_file).exists()
            with open(output_file, "a+", newline="\n", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(headers)
                writer.writerows(rows)
            logger.info(
                f"{self.__class__.RECORD_TYPE} IDs saved to: {output_file}".capitalize()
            )
        else:
            logger.warning(f"No {self.__class__.RECORD_TYPE} IDs found.")

    @classmethod
    @abstractmethod
    def append_row_data(
        cls, item: dict[str, Any], rows: list[list[str]], headers: list[str], criterion2: str
    ) -> None:
        """
        Extract row data from the item and append record ids in inventory.
        """
        pass

    @classmethod
    @abstractmethod
    def get_list_headers(cls) -> list[str]:
        """
        Get headers for the list of records in a sheet.
        Returns:
            Dict[str, Any]: Headers for the receipt list.
        """
        return []

    @classmethod
    @abstractmethod
    def check_refs(cls, params: dict[str, Any]) -> None:
        """
        Validate required parameters.
        Args:
            params (Dict[str, Any]): Parameters to validate.
        Raises:
            ValueError: If any required parameter is missing.
        """
        pass

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
        try:
            with open(file_path, "r", encoding="utf-8") as infile:
                reader = csv.reader(infile)
                for row in reader:
                    if row[0] not in seen:  # Check if the first column value is unique
                        seen.add(row[0])  # _id or id column
                        unique_rows.append(row)
        except FileNotFoundError:
            logger.error(f"The input file '{file_path}' does not exist.")

        if unique_rows:
            # Overwrite the file with the unique rows
            with open(file_path, "w", encoding="utf-8") as outfile:
                writer = csv.writer(outfile)
                writer.writerows(unique_rows)

        logger.info(f"Duplicates removed in place. File updated: {file_path}")

    def fetch_details(
        self, base_url: str, refs: dict[str, Any], verbose: bool = False
    ) -> None:
        """
        Fetch detailed receipt data from the API.
        Args:
            base_url (str): API endpoint URL.
            refs (Dict[str, Any]): Receipt references.
            verbose (bool): Whether to print detailed logs.
        """
        date_time_str = datetime.now().strftime("%Y%m%d_%H_%M")
        self.__class__.check_refs(refs)
        headers = self.__class__.get_list_headers()
        url = self.get_full_url(base_url, refs, headers)
        data = self.fetch_data(
            url,
            params={},
            referer=self.__class__.REFERER_URL,
            verbose=verbose,
        )
        (
            self.save_data_to_file(
                data,
                f"{date_time_str}-{CarrefourBaseExtractor.BRAND_NAME}_{self.__class__.RECORD_TYPE}_{refs[headers[0]]}_details.json",
            )
            if data
            else logger.warning(
                f"No data found for {self.__class__.RECORD_TYPE} {refs[headers[0]]}."
            )
        )

    def get_full_url(self, base_url: str, refs: str, headers: str = list[str]) -> str:
        """
        Get the full url with referenced headers in payload
        """
        return f"{base_url}/{refs[headers[0]]}"

    def fetch_details_from_file(
        self,
        base_url: str,
        input_file: str,
        criterion: str = datetime.now().strftime("%Y%m%d"),
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
        headers = self.get_list_headers()
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # criterion based on date
                    if row.get("dateExtraction") != criterion:
                        continue
                    # criterion based on id
                    if not row.get(headers[0]):
                        continue
                    self.fetch_details(base_url, row, verbose=verbose)
        except FileNotFoundError:
            logger.error(f"The input file '{input_file}' does not exist.")


class CarrefourReceiptExtractor(CarrefourBaseExtractor):
    """
    Wrapper class for Carrefour receipts
    """

    RECORD_TYPE = "receipt"
    REFERER_URL = "https://www.carrefour.fr/mon-compte/mes-achats/en-magasin"
    PARAM_KEYS = ["loyaltyCardNumber", "loyaltyCardType"]
    API_URL = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
    API_URL_INDIV = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipt"

    @classmethod
    def append_row_data(
        cls,
        item: dict[str, Any],
        rows: list[list[str]],
        headers: list[str],
        criterion2: str,
    ):
        """
        Append record ids in inventory.
        """
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

    @classmethod
    def get_list_headers(cls) -> list[str]:
        """
        Get headers for the receipt list in a sheet.
        Returns:
            Dict[str, Any]: Headers for the receipt list.
        """
        return ["id", "gln", "dateKey", "receiptNumber"]

    @classmethod
    def check_refs(cls, params: dict[str, Any]) -> None:
        """
        Validate required references.
        Args:
            params (Dict[str, Any]): Parameters to validate.
        Raises:
            ValueError: If any required parameter is missing.
        """
        required_params = ["gln", "dateKey", "receiptNumber"]
        check_keys(params, required_params)

    def get_full_url(self, base_url: str, refs: list[str], headers: list[str]):
        return f"{base_url}/{refs[headers[1]]}/{refs[headers[2]]}/{refs[headers[3]]}"


class CarrefourOrderExtractor(CarrefourBaseExtractor):
    """
    Wrapper class for Carrefour orders.
    """

    RECORD_TYPE = "order"
    REFERER_URL = "https://www.carrefour.fr/mon-compte/mes-achats/en-ligne"
    PARAM_KEYS = ["startDate", "endDate"]
    API_URL = "https://www.carrefour.fr/api/user/orders"
    API_URL_INDIV = "https://www.carrefour.fr/api/user/orders"

    @classmethod
    def append_row_data(
        cls,
        item: dict[str, Any],
        rows: list[list[str]],
        headers: list[str],
        criterion2: str,
    ):
        """
        Append record ids in inventory.
        """
        if "data" in item:
            for order in item["data"]:
                rows.append(
                    [
                        order.get("attributes").get(headers[0]),
                        criterion2,  # a criterion by default the extraction date
                    ]
                )

    @classmethod
    def get_list_headers(cls) -> list[str]:
        """
        Get headers for the order list in a sheet.
        Returns:
            Dict[str, Any]: Headers for the receipt list.
        """
        return ["orderNumber"]

    @classmethod
    def check_refs(cls, params: dict[str, Any]) -> None:
        """
        Validate required references.
        Args:
            params (Dict[str, Any]): Parameters to validate.
        Raises:
            ValueError: If any required parameter is missing.
        """
        required_params = ["orderNumber"]
        check_keys(params, required_params)


class CarrefourLoyaltyExtractor(CarrefourBaseExtractor):
    """
    Wrapper class extractor for Carrefour loyalty data.
    """

    RECORD_TYPE = "loyalty_operation"
    REFERER_URL = "https://www.carrefour.fr/mon-compte/mes-achats/en-magasin"
    PARAM_KEYS = ["loyaltyCardNumber", "loyaltyCardType"]
    API_URL = "https://www.carrefour.fr/api/user/secured/loyalty/transactions"
    API_URL_INDIV = "https://www.carrefour.fr/api/user/secured/loyalty/transactions"

    def fetch_paginated_data(
        self,
        url: str,
        params: dict[str, Any],
        max_scrolls: int = MAX_SCROLLS,
        verbose: bool = False,
    ):
        """
        Fetch all the loyalty details given a reference date in params.
        Args:
            url (str): API endpoint URL.
            params (Dict[str, Any]): Initial query parameters.
            verbose (bool): Whether to print detailed logs.
        """
        self.__class__.check_params(params)
        end_date = datetime.now()
        date_time_str = end_date.strftime("%Y%m%d_%H_%M")
        date = params.get("date")
        if not date:
            raise ValueError("The date is None.")
        month = int(date[:2])
        year = int(date[-4:])
        logger.info("Fetching initial data...")
        current_date = datetime(
            year=year, month=month, day=1
        )  # Start with the initial date
        end_date_obj = datetime(
            year=end_date.year, month=end_date.month, day=1
        )  # Normalize end_date to the first day of the month
        scroll = 0  # artificial pages
        try:
            while current_date < end_date_obj and scroll < max_scrolls:
                # Format the date as "MM/01/YYYY"
                params["date"] = current_date.strftime(
                    "%m/01/%Y"
                )  # Use strftime for consistent formatting

                # Fetch data
                data = self.fetch_data(
                    url,
                    params,
                    referer=self.__class__.REFERER_URL,
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
                # add the id YYYYMM for year and month (unique identifier in loyalty balance)
                data["_id"] = current_date.strftime("%Y%m")  # Use strftime to write YYYYMM only
                self.save_data_to_file(
                    data,
                    f"{date_time_str}-{formatted_date}_{CarrefourBaseExtractor.BRAND_NAME}_{self.__class__.RECORD_TYPE}s_all.json",
                )

                # Move to the next month
                current_date = CarrefourLoyaltyExtractor._increment_month(current_date)
                scroll += 1

        except Exception as e:
            logger.error(f"Error during data fetching: {e}")

    @staticmethod
    def _increment_month(current_date: datetime) -> datetime:
        """
        Increment the month, rolling over to the next year if necessary
        """
        if current_date.month == 12:
            return current_date.replace(year=current_date.year + 1, month=1)
        return current_date.replace(month=current_date.month + 1)

    @classmethod
    def append_row_data(
        cls,
        item: dict[str, Any],
        rows: list[list[str]],
        headers: list[str],
        criterion2: str,
    ):
        """
        Append record ids in inventory.
        """
        if "history" in item:
            for op in item["history"]:
                rows.append(
                    [
                        op.get(headers[0]),
                        criterion2,  # a criterion by default the extraction date
                    ]
                )

    @classmethod
    def get_list_headers(cls) -> list[str]:
        """
        Get headers for the record list.
        Returns:
            Dict[str, Any]: Headers for the receipt list.
        """
        return ["operationId"]

    @classmethod
    def check_refs(cls, params: dict[str, Any]) -> None:
        """
        Validate required references.
        Args:
            params (Dict[str, Any]): Parameters to validate.
        Raises:
            ValueError: If any required parameter is missing.
        """
        required_params = ["operationId"]
        check_keys(params, required_params)


def main(record_type: str):
    """
    Extract the details from Carrefour receipts according to some criterions (automated or not). Work for all record types.
    """
    params = get_fetch_payload(record_type)
    list_params = []
    for v in params.values():
        if isinstance(v, list):
            list_params = unpack_dict_zip(params)
            break

    max_scrolls = MAX_SCROLLS

    # Initialize the extractor
    factory = CarrefourDataExtractorFactory(cookies_file=COOKIES_FILE)

    extractor = factory.get_extractor(record_type)

    # # Step 0: Perform login
    # login = AccountLogin()
    # handler.perform_login("https://www.carrefour.fr/login")

    # Step 1: Fetch paginated data or whole data
    if len(list_params) > 0:
        for p in list_params:
            extractor.fetch_paginated_data(
                extractor.__class__.API_URL, p, max_scrolls=max_scrolls, verbose=False
            )
    else:
        extractor.fetch_paginated_data(
            extractor.__class__.API_URL, params, max_scrolls=max_scrolls, verbose=False
        )

    # Step 2: Extract IDs
    extractor.extract_ids(
        criterion1=f"{CarrefourBaseExtractor.BRAND_NAME}_{record_type}s_",
        criterion2=datetime.now().strftime("%Y%m%d"),
        output_file=f"{DATA_DIRECTORY}/{record_type}_ids.csv",
    )
    CarrefourBaseExtractor.remove_duplicates_from_list(
        f"{DATA_DIRECTORY}/{record_type}_ids.csv"
    )

    # Step 3: Fetch receipt details
    extractor.fetch_details_from_file(
        base_url=extractor.__class__.API_URL_INDIV,
        input_file=f"{DATA_DIRECTORY}/{record_type}_ids.csv",
        criterion=datetime.now().strftime("%Y%m%d"),
        verbose=False,
    )


def get_fetch_payload(record_type: str):
    """
    Customizable function as to select between various parameters to feed in curl request.
    """
    match record_type:
        case "receipt":
            config = AccountLogin.load_secrets(
                path_to_secrets=f"{DATA_DIRECTORY}/secrets.yml"
            )

            return {
                "loyaltyCardNumber": [
                    config.get("loyaltyCardNumber", ""),
                    config.get("passCardNumber", ""),
                ],
                "loyaltyCardType": ["LOYALTY", "PASS_MASTERCARD"],
            }
        case "order":
            end_date = datetime.now().strftime("%Y-%m-%d")  # YYYY-MM-DD
            return {
                "startDate": unquote(
                    "2022-01-01T00%3A00%3A00.000Z"
                ),  # peculiar filter in carrefour.fr
                "endDate": unquote(f"{end_date}T00%3A00%3A00.000Z"),
            }
        case "loyalty_operation":
            return {"date": "04/01/2022"}
        case _:
            logger.warning(
                "Please choose between record_type: 'receipt', 'order' or 'loyalty_operation'."
            )


class CarrefourDataExtractorFactory:
    """
    Factory class to create extractor instances for receipts, orders, or loyalty operations.
    """

    def __init__(
        self, cookies_file: str = COOKIES_FILE, dst_folder: str = DATA_DIRECTORY
    ) -> None:
        """
        Initialize the factory with default configurations.

        Args:
            cookies_file (str): Path to the cookies file.
            dst_folder (str): Directory where extracted data will be saved.
        """
        self.cookies_file = cookies_file
        self.dst_folder = dst_folder

    def get_extractor(self, type_: str):
        """
        Get an extractor instance based on the specified type.

        Args:
            type_ (str): Type of extractor ('receipt', 'order', or 'loyalty_operation').
                Must match the ``record_type`` used by ``get_fetch_payload``.

        Returns:
            BaseExtractor: An instance of the appropriate extractor class.

        Raises:
            ValueError: If an invalid type is provided.
        """
        match type_:
            case "receipt":
                return CarrefourReceiptExtractor(self.cookies_file, self.dst_folder)
            case "order":
                return CarrefourOrderExtractor(self.cookies_file, self.dst_folder)
            case "loyalty_operation":
                return CarrefourLoyaltyExtractor(self.cookies_file, self.dst_folder)
            case _:
                raise ValueError(
                    "Invalid type. Choose 'receipt', 'order', or 'loyalty_operation'."
                )


# Main execution
if __name__ == "__main__":
    main(record_type="receipt")
