"""
DEPRECATED: Use user_api_extractor instead.
TODO: Use SeleniumBase and type instead of filling from playwright
"""

import asyncio
from http.cookiejar import CookieJar, Cookie
import logging
import random
import time
from typing import Dict, Any, Optional
from urllib3.util.retry import Retry
from urllib.parse import urlencode


import httpx
from httpx import HTTPTransport
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright
import requests
from requests.adapters import HTTPAdapter
from requests.cookies import create_cookie
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import undetected_chromedriver as uc
import yaml

from carrefour_receipts_api import config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class NetworkScraper:
    """
    A web scraper that handles login, cookie management,
    user-agent rotation, network interception, and API data fetching.
    """

    def __init__(self, login_webpage: str, *args, **kwargs):
        """
        Initialize the scraper with login_webpage and credentials.
        Credentials can be provided as keyword arguments or a dictionary.
        """
        self.login_webpage = login_webpage
        if args and isinstance(args[0], dict):
            user_id = args[0]
            if "username" not in user_id or "password" not in user_id:
                raise KeyError("Missing required keys in user_id: 'username' and/or 'password'")
            self.username, self.password = user_id["username"], user_id["password"]
        elif kwargs:
            self.username = kwargs.get("username")
            self.password = kwargs.get("password")
            if not self.username or not self.password:
                raise ValueError("Missing required keyword arguments: 'username' and/or 'password'")
        elif (args and isinstance(args[0], str)) or (not args and not kwargs):
            secrets = self._load_credentials(args[0] if args and isinstance(args[0], str) else "secrets.yml")
            self.username, self.password = secrets.get("username"), secrets.get("password")
        else:
            raise ValueError("No valid input provided")
        self.browser = None
        self.context = None
        self.page = None
        self.cookies = []
        if not self.username or not self.password:
            raise ValueError("Username and password should not be empty")

    def _load_credentials(self, path_to_secrets: str = "secrets.yml") -> Dict[str, Any]:
        """Load credentials from a YAML file."""
        logger.info(f"Loading configuration from: {path_to_secrets}")
        try:
            with open(path_to_secrets, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if not isinstance(config, dict):
                raise ValueError("Configuration file must contain a dictionary at the top level.")
            return config
        except FileNotFoundError as e:
            logger.error(f"Configuration file '{path_to_secrets}' not found.")
            raise e
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML format in configuration file '{path_to_secrets}': {e}")
            raise e
    async def login(self, load_cookies: bool = False) -> None:
        """Perform login using Playwright asynchronously."""
        try:
            await self._setup_browser()
            await self.page.goto(self.login_webpage)
            logger.info(f"Navigated to login page: {self.login_webpage}")

            # Perform login actions
            elems = self.get_login_elements()
            await self.page.fill(f"#{elems['username']}", self.username)
            await asyncio.sleep(1.5)
            await self.page.fill(f"#{elems['password']}", self.password)
            await self.page.click(f"#{elems['login_button']}")
            await asyncio.sleep(2)  # Wait for login to complete
            logger.info("Authentication done.")

            # Extract cookies and User-Agent after login
            if load_cookies:
                self.cookies = await self.context.cookies()
                logger.info(f"Extracted cookies: {self.cookies}")
        except Exception as e:
            logger.error(f"Error during login: {e}")
            raise
    
    def fetch_httpx_data(
        self,
        url: str,
        params: Dict[str, Any],
        headers: Dict[str, Any],
        proxies_list: Optional[list[str]] = None,
    ) -> httpx.Response:
        """
        Fetch data from an API with robust error handling, retry logic, and proxy support using HTTPX.
        """
        RETRY_STRATEGY = Retry(
            total=5,  # Maximum number of retries
            backoff_factor=1,  # Exponential backoff
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these HTTP status codes
        )
        proxy = None
        if proxies_list:
            random_proxy = random.choice(proxies_list)
            proxy = f"http://{random_proxy}"
        transport = httpx.HTTPTransport(
            retries=RETRY_STRATEGY, verify=True
        )  # Ensure SSL verification is enabled
        with httpx.Client(transport=transport, proxy=proxy) as client:
            try:
                response = client.get(
                    url,
                    params=params,
                    headers=headers,
                    cookies=self.get_httpx_cookies(),
                )
                response.raise_for_status()  # Raise an exception for HTTP errors
                logger.info(f"Fetched data using HTTPX from {url} with parameters: {params}")
                return response
            except httpx.HTTPStatusError as err:
                logger.error(f"HTTP error occurred: {err}")
                raise
            except Exception as err:
                logger.error(f"Error fetching data using HTTPX: {err}")
                raise


    async def _setup_browser(self, proxy: Optional[str] = None) -> None:
        """Set up the Playwright browser and context asynchronously."""
        try:
            self.playwright = await async_playwright().start()
            launch_options = {
                "headless": True,
                "proxy": {"server": proxy} if proxy else None,
            }
            self.browser = await self.playwright.chromium.launch(**launch_options)
            self.context = await self.browser.new_context(user_agent=self._get_random_user_agent())
            self.page = await self.context.new_page()
            logger.info("Playwright browser initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Playwright browser: {e}")
            raise

    
    def _get_random_user_agent(self) -> str:
        """Generate a random User-Agent string."""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/120.0",
        ]
        return random.choice(user_agents)

    def _intercept_network_requests(self, route, request):
        """
        Intercept and modify network requests for advanced control.
        This method can throttle network speed, block specific resources, or log requests.
        """
        logger.info(f"Intercepted request: {request.url}")
        # Example: Block requests to specific domains
        if "ads.example.com" in request.url:
            logger.info(f"Blocking request to: {request.url}")
            route.abort()
        else:
            route.continue_()

    def get_login_elements(self) -> Dict[str, Any]:
        """Return the element keys for login."""
        return {
            "username": "idToken1",
            "password": "idToken2",
            "login_button": "loginButton_0",
        }

    # def login(self, load_cookies=False) -> None:
    #     """Perform login using Playwright."""
    #     try:
    #         self._setup_browser()
    #         self.page.goto(self.login_webpage)
    #         logger.info(f"Navigated to login page: {self.login_webpage}")

    #         # Perform login actions
    #         elems = self.get_login_elements()
    #         self.page.fill(f"#{elems['username']}", self.username)
    #         time.sleep(1.5)
    #         self.page.fill(f"#{elems['password']}", self.password)
    #         self.page.click(f"#{elems['login_button']}")
    #         time.sleep(2)  # Wait for login to complete
    #         logger.info("Authentication done.")

    #         # Extract cookies and User-Agent after login
    #         if load_cookies:
    #             self.cookies = self.context.cookies()
    #             logger.info(f"Extracted cookies: {self.cookies}")
    #     except Exception as e:
    #         logger.error(f"Error during login: {e}")
    #         raise

    def get_to_referer(self, referer: str = "https://www.carrefour.fr/mon-compte/mes-achats/en-magasin") -> None:
        """
        Navigate to target page and collect cookies there.
        """
        try:
            self.page.goto(referer)
            logger.info(f"Navigated to referer page: {referer}")

            # Simulate mouse movement to mimic human interaction
            self.page.mouse.move(random.randint(100, 500), random.randint(100, 500))
            time.sleep(random.uniform(1, 5))  # Random delay to mimic human behavior

            # Extract cookies
            self.cookies = self.context.cookies()
            logger.info(f"Extracted cookies: {self.cookies}")
        except Exception as e:
            logger.error(f"Error navigating to referer page: {e}")
            raise

    @staticmethod
    def create_httpx_cookie(cookie: Dict[str, Any]) -> Cookie:
        if not cookie:
            raise ValueError("The cookie is empty.")
        cookie_obj = Cookie(
            version=0,
            name=cookie["name"],
            value=cookie["value"],
            port=None,
            port_specified=False,
            domain=cookie["domain"],
            domain_specified=bool(cookie["domain"]),
            domain_initial_dot=cookie["domain"].startswith("."),
            path=cookie["path"],
            path_specified=bool(cookie["path"]),
            secure=True if cookie.get("secure", "false") == "true" else False,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={"HttpOnly": cookie.get("httpOnly")},
            rfc2109=False,
        )
        return cookie_obj

    def get_httpx_cookies(self) -> CookieJar:
        """Convert Playwright cookies into an HTTPX-compatible CookieJar."""
        cookie_jar = CookieJar()
        if self.cookies:
            for cookie in self.cookies:
                cookie_obj = self.create_httpx_cookie(cookie)
                cookie_jar.set_cookie(cookie_obj)
        return cookie_jar


    def end_session(self):
        """Close the browser session and clean up resources."""
        if self.browser:
            self.browser.close()
            self.playwright.stop()
            logger.info("Playwright browser session ended.")


# # Example Usage
# if __name__ == "__main__":
#     LOGIN_PAGE = (
#         "https://moncompte.carrefour.fr/iam/XUI/#login/&goto=http%3A%2F%2Fmoncompte.carrefour.fr%2Fiam%2Foauth2%2FCarrefourConnect%2Fauthorize%3Fclient_id%3Dcarrefour_onecarrefour_web%26redirect_uri%3Dhttps%253A%252F%252Fwww.carrefour.fr%252Flogin%252Fcheck%26response_type%3Dcode%26scope%3Dopenid%2520iam%2520register-aHR0cHM6Ly93d3cuY2FycmVmb3VyLmZyL21vbi1jb21wdGUvaW5zY3JpcHRpb24%253D&realm=%2FCarrefourConnect"
#     )
#     USERNAME = "your_username"
#     PASSWORD = "your_password"

#     # Arguments for HTTPX request
#     url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
#     params = {"loyaltyCardNumber": config.LOYALTY_CARD_NUMBER, "loyaltyCardType": "LOYALTY"}
#     HEADERS = {
#         "Accept": "application/json, text/plain, */*",
#         "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
#         "Sec-Fetch-Dest": "empty",
#         "Sec-Fetch-Mode": "cors",
#         "Sec-Fetch-Site": "same-origin",
#         "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0",
#         "X-Requested-With": "XMLHttpRequest",
#         "Referrer": "https://www.carrefour.fr/mon-compte/mes-achats/en-magasin",
#         "Referrer-policy": "strict-origin-when-cross-origin",
#     }

#     scraper = NetworkScraper(LOGIN_PAGE, username=USERNAME, password=PASSWORD)
#     scraper.login(load_cookies=True)
#     scraper.get_to_referer()

#     # Use the extracted cookies and User-Agent for API calls
#     headers = HEADERS | {"User-Agent": scraper._get_random_user_agent()}
#     data = scraper.fetch_httpx_data(url, params, headers, proxies_list=None)
#     scraper.end_session()

#     print(data.text)
#     print(data.json())


class WebScraper:
    """
    A web scraper that handles login, cookie management,
    user-agent rotation, and API data fetching and parsing JSON.
    """

    def __init__(self, login_webpage: str, *args, **kwargs):
        """
        Init the web scraper with login_webpage and provided credentials.

        The function accepts credentials in two formats:
        1. As keyword arguments: username="gip", password="kop".
        2. As a dictionary: user_id={"username": "gip", "password": "kop"}.

        Args:
            login_webpage: Authentication page
            *args: Positional arguments (e.g., a dictionary for user_id).
            **kwargs: Keyword arguments (e.g., username and password).

        Returns:
            A tuple containing the username and password.
        """
        self.login_webpage = login_webpage
        # Check if the first positional argument is a dictionary
        if args and isinstance(args[0], dict):
            user_id = args[0]
            if "username" not in user_id or "password" not in user_id:
                raise KeyError(
                    "Missing required keys in user_id: 'username' and/or 'password'"
                )
            username, password = user_id["username"], user_id["password"]
        elif kwargs:
            # Extract username and password from keyword arguments
            username = kwargs.get("username")
            password = kwargs.get("password")
            if not username or not password:
                raise ValueError(
                    "Missing required keyword arguments: 'username' and/or 'password'"
                )
        elif (args and isinstance(args[0], str)) or (not args and not kwargs):
            secrets = self._load_credentials(
                path_to_secrets=(
                    args[0] if args and isinstance(args[0], str) else "secrets.yml"
                )
            )
            username = secrets.get("username")
            password = secrets.get("password")
        else:
            raise ValueError("No valid input provided")

        self.username = username
        self.password = password
        self.driver = None
        self.cookies = []

        if not self.username and not self.password:
            raise ValueError("Username and password should not be empty")

    def _load_credentials(self, path_to_secrets: str = "secrets.yml") -> Dict[str, Any]:
        """
        Load configuration from a YAML file. It indicates the location of training data and annotations

        Args:
            path_to_secrets (Path): Path to the YAML configuration file.

        Returns:
            Dict[str, Any]: Configuration as a dictionary.

        Raises:
            FileNotFoundError: If the configuration file is not found.
            ValueError: If the YAML file has invalid syntax.
        """
        logger.info(f"Loading configuration from: {path_to_secrets}")
        try:
            with open(path_to_secrets, "r", encoding="utf-8") as f:
                config = yaml.safe_load(
                    f
                )  # Use safe_load to avoid arbitrary code execution
            if not isinstance(config, dict):
                raise ValueError(
                    "Configuration file must contain a dictionary at the top level."
                )
            return config  # a dictionary
        except FileNotFoundError as e:
            logger.error(f"Configuration file '{path_to_secrets}' not found.")
            raise e
        except yaml.YAMLError as e:
            logger.error(
                f"Invalid YAML format in configuration file '{path_to_secrets}': {e}"
            )
            raise e
    
    def login(self, load_cookies : bool = False) -> None:
        """Perform login using Selenium."""
        try:
            self._setup_driver()
            self.driver.get(self.login_webpage)
            logger.info(f"Navigated to login page: {self.login_webpage}")

            # Perform login actions
            elems = self.get_login_elements()
            wait = WebDriverWait(self.driver, 20)
            username_field = wait.until(
                EC.presence_of_element_located((By.ID, elems["username"]))
            )
            # username_field = self.driver.find_element("idToken1")
            password_field = wait.until(
                EC.presence_of_element_located((By.ID, elems["password"]))
            )
            # password_field = self.driver.find_element("idToken2")
            username_field.send_keys(self.username)
            time.sleep(1.5)
            password_field.send_keys(self.password)

            login_button = wait.until(
                EC.presence_of_element_located((By.ID, elems["login_button"]))
            )
            time.sleep(2)
            login_button.click()
            logger.info("Authentication done.")

            # Wait for login to complete
            # wait.until(EC.presence_of_all_elements_located((By.ID, "header")))
            time.sleep(1)
            logger.info("Login completed successfully.")
            # Extract cookies and User-Agent after login
            if load_cookies:
                self.cookies = self.driver.get_cookies()
                logger.info(f"Extracted cookies: {self.cookies}")
        except Exception as e:
            logger.error(f"Error during login: {e}")
            raise
        # finally:
        #     if self.driver:
        #         self.driver.quit()

    def fetch_requests_data(
        self,
        url: str,
        params: Dict[str, Any],
        headers: Dict[str, Any],
        cookies: list[dict],
        proxies_list: Optional[list[str]] = None,
    ) -> requests.Response:
        """
        Fetch data from an API with robust error handling, retry logic, and proxy support.
        Note: Does not support samesite cookies.
        """
        # USER_AGENTS = [
        #     "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0",
        #     "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0 Safari/537.36",
        #     "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
        #     "Mozilla/5.0 (Macintosh Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
        # ]

        RETRY_STRATEGY = Retry(
            total=5,  # Maximum number of retries
            backoff_factor=1,  # Exponential backoff
            status_forcelist=[
                429,
                500,
                502,
                503,
                504,
            ],  # Retry on these HTTP status codes
        )

        proxies = None
        if proxies_list:
            random_proxy = random.choice(proxies_list)
            proxies = {
                "http": f"http://{random_proxy}",
                "https": f"http://{random_proxy}",
            }

        with requests.Session() as session:
            # session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
            session.mount("https://", HTTPAdapter(max_retries=RETRY_STRATEGY))
            self.set_requests_cookies(session)
            # update the header with the user agent used by the Selenium driver
            try:
                response = session.get(
                    url,
                    params=params,
                    headers=headers,
                    cookies=cookies,
                    proxies=proxies,
                )
                response.raise_for_status()
                logger.info(
                    f"Fetched data using requests from {url} with parameters: {params}"
                )
                return response
            except requests.exceptions.HTTPError as err:
                logger.error(f"HTTP error occurred: {err}")
                raise
            except Exception as err:
                logger.error(f"Error fetching data using requests: {err}")
                raise

    def fetch_requests_pages_scroll(
        self,
        url: str,
        common_params: Dict[str, Any],
        headers: Dict[str, Any],
        cookies: list[dict],
        max_scrolls: int = 10,
        proxies_list: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch all data by scrolling from url to url.
        Note: Does not support samesite cookies.
        """
        response = self.fetch_requests_data(
            url, common_params, headers, cookies, proxies_list
        )
        json_data = response.json()
        scrollPage = self.get_scrollPage(json_data)
        scrollHash = self.get_scrollHash(json_data)
        delay = random.randint(1, 3)  # Random delay to mimic human behavior
        time.sleep(delay)
        scrolls = 0
        while scrollHash and scrolls < max_scrolls:
            response = self.fetch_requests_data(
                url,
                {
                    **common_params,
                    "scrollPage": scrollPage,
                    "scrollHash": scrollHash,
                },
                headers,
                cookies,
                scrolls,
                proxies_list,
            )
            json_data.update(response.json())
            scrolls += 1
            delay = random.randint(1, 3)  # Random delay to mimic human behavior
            time.sleep(delay)
        return json_data

    def fetch_httpx_data(
        self,
        url: str,
        params: Dict[str, Any],
        headers: Dict[str, Any],
        cookies: httpx.Cookies,
        proxies_list: Optional[list[str]] = None,
    ) -> httpx.Response:
        """
        Fetch data from an API with robust error handling, retry logic, and proxy support using HTTPX.
        Note: HTTPX supports samesite cookies better than Requests.
        """
        # RETRY STRATEGY
        RETRY_STRATEGY = Retry(
            total=5,  # Maximum number of retries
            backoff_factor=1,  # Exponential backoff
            status_forcelist=[
                429,
                500,
                502,
                503,
                504,
            ],  # Retry on these HTTP status codes
        )

        # PROXY HANDLING
        proxy = None
        if proxies_list:
            random_proxy = random.choice(proxies_list)
            proxy = f"http://{random_proxy}"
        # HTTPX TRANSPORT WITH RETRY LOGIC
        transport = HTTPTransport(
            retries=RETRY_STRATEGY, verify=True
        )  # Ensure SSL verification is enabled

        # HTTPX SESSION SETUP
        with httpx.Client(transport=transport, proxy=proxy) as client:
            try:
                # Perform the GET request
                response = client.get(
                    url,
                    params=params,
                    headers=headers,
                    cookies=cookies,
                )
                response.raise_for_status()  # Raise an exception for HTTP errors
                logger.info(
                    f"Fetched data using HTTPX from {url} with parameters: {params}"
                )
                return response
            except httpx.HTTPStatusError as err:
                logger.error(f"HTTP error occurred: {err}")
                raise
            except Exception as err:
                logger.error(f"Error fetching data using HTTPX: {err}")
                raise

    def fetch_selenium_data(
        self,
        url: str,
        params: Dict[str, Any],
        referer: str = "https://www.carrefour.fr/mon-compte/mes-achats/en-magasin",
    ):
        """
        Fetch data from an API using Selenium (headless and all headers)
        Note: May fail to bypass anti-bot measures (not natural navigation, some header inconsistencies, cookies accessed by Javscript unauthorized).
        """
        query_string = urlencode(params)
        full_url = f"{url}?{query_string}"
        time.sleep(2)

        def make_request(driver, full_url: str, referer: str):
            """
            Make a request using Selenium WebDriver by injecting a JavaScript fetch request.
            """
            try:
                # Define the fetch request as a JavaScript string
                js_fetch_script = """
                const url = "URL_PLACEHOLDER";
                const options = {
                    method: "GET",
                    headers: {
                        "accept": "application/json, text/plain, */*"
                    },
                    referrer: "REFERER_PLACEHOLDER",
                    credentials: "include"
                };

                // Return a Promise that resolves with the fetch response
                return fetch(url, options)
                    .then(response => response.text())  // Parse the response as text
                    .then(data => data)                 // Return the parsed JSON
                    .catch(error => { throw new Error(error); });  // Handle errors
                """

                js_fetch_script = js_fetch_script.replace("URL_PLACEHOLDER", full_url)
                js_fetch_script = js_fetch_script.replace(
                    "REFERER_PLACEHOLDER", referer
                )
                # Log the generated JavaScript for debugging
                logger.debug(f"Generated JavaScript: {js_fetch_script}")

                # Execute the JavaScript fetch request
                response_data = driver.execute_script(js_fetch_script)

                # Log the fetched data
                logger.info(f"Fetched data from {full_url}")

                return response_data
            except Exception as err:
                logger.error(f"Error fetching data with Selenium: {err}")
                raise

            finally:
                # Clean up and close the WebDriver
                driver.quit()

        try:
            # Navigate to the domain to set cookies
            # self.driver.get(url.split('?')[0])
            # Add cookies to the driver

            # Make the request and return the response (maybe jsonify …)
            return make_request(self.driver, full_url, referer)
        except Exception as err:
            logging.warning(f"Attempt to fetch using Selenium failed")
        finally:
            # Close the WebDriver to free resources
            # close the driver after 3 seconds
            time.sleep(3)
            if self.driver:
                self.driver.quit()

    def _setup_driver(self, proxy: Optional[str] = None) -> None:
        """Set up the Selenium WebDriver with custom options."""
        # user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.140 Safari/537.36"
        brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        try:
            chrome_options = uc.ChromeOptions()
            chrome_options.headless = True
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--start-maximized")
            if proxy:
                chrome_options.add_argument(f"--proxy-server=http://{proxy}")
            # chrome_options.add_argument(f"user-agent={user_agent}")
            self.driver = uc.Chrome(
                use_subprocess=True,
                options=chrome_options,
                browser_executable_path=brave_path,
            )
            logger.info("Selenium WebDriver initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def get_login_elements(self) -> Dict[str, Any]:
        """Return the element keys in loginpage"""
        return {
            "username": "idToken1",
            "password": "idToken2",
            "login_button": "loginButton_0",
        }

    def get_user_agent(self) -> str:
        """Retrieve the current User-Agent from the browser."""
        user_agent = self.driver.execute_script("return navigator.userAgent;")
        logger.info(f"Current User-Agent: {user_agent}")
        return user_agent

    def get_to_referer(self, referer: str = "https://www.carrefour.fr/mon-compte/mes-achats/en-magasin") -> None:
        """
        Get to target page and collect cookies there
        """
        # Step 1: Navigate to the target URL (or any page on the same domain)
        time.sleep(random.uniform(1, 5))
        self.driver.get(referer) # fully loaded
        # WebDriverWait(self.driver, 10).until(EC.presence_of_all_elements_located((By.ID, "main")))

        # Simulate mouse movement to mimic human interaction
        actions = ActionChains(self.driver)
        actions.move_by_offset(100, 100).perform()

        # Wait for the Turnstile challenge to resolve
        time.sleep(10)  # Adjust based on observed behavior
        # time.sleep(random.uniform(1, 4))
        logger.info(f"Going to {referer}.")
        print(self.driver.page_source)
        # Step 2: Get the cookies
        self.cookies = self.driver.get_cookies()
        logger.info(f"Extracted cookies: {self.cookies}")

    @staticmethod
    def get_scrollPage(json_data: Dict[str, Any]) -> str:
        return json_data["meta"].get("scrollPage", "")

    @staticmethod
    def get_scrollHash(json_data: Dict[str, Any]) -> str:
        return json_data["meta"].get("scrollHash", "")

    @staticmethod
    def create_requests_cookie(cookie: Dict[str, Any]) -> Any:
        if not cookie:
            raise ValueError("The cookie is empty.")
        cleaned_cookie = {k: v for k, v in cookie if k not in ["httpOnly", "sameSite"]}
        rest_cookies = {k: v for k, v in cookie if k == "httpOnly"}
        session_cookie = create_cookie(**cleaned_cookie, rest=rest_cookies)
        return session_cookie

    def set_requests_cookies(self, session: requests.Request) -> None:
        if self.cookies:
            for cookie in self.cookies:
                session.cookies.set_cookie(self.create_requests_cookie(cookie))

    @staticmethod
    def create_httpx_cookie(cookie: Dict[str, Any]) -> Cookie:
        if not cookie:
            raise ValueError("The cookie is empty.")
        cookie_obj = Cookie(
            version=0,
            name=cookie["name"],
            value=cookie["value"],
            port=None,
            port_specified=False,
            domain=cookie["domain"],
            domain_specified=bool(cookie["domain"]),
            domain_initial_dot=cookie["domain"].startswith("."),
            path=cookie["path"],
            path_specified=bool(cookie["path"]),
            secure=True if cookie.get("secure", "false") == "true" else False, # convert string to boolean
            expires=None,
            discard=True,
            comment=None,
            comment_url= None,
            rest={"HttpOnly": cookie.get("httpOnly")},
            rfc2109=False
        )
        return cookie_obj

    def get_httpx_cookies(self) -> CookieJar:
        cookie_jar = CookieJar()
        if self.cookies:
            for cookie in self.cookies:
                cookie_obj = self.create_httpx_cookie(cookie)
                cookie_jar.set_cookie(cookie_obj)
        return cookie_jar

    def lazy_browsing(self):
        time.sleep(3.5)
        self.driver.execute_script("window.scrollTo(0, 700)")

    def end_session(self):
        if self.driver:
            self.driver.quit()


# Example Usage
if __name__ == "__main__":
    LOGIN_PAGE = "https://moncompte.carrefour.fr/iam/XUI/#login/&goto=http%3A%2F%2Fmoncompte.carrefour.fr%2Fiam%2Foauth2%2FCarrefourConnect%2Fauthorize%3Fclient_id%3Dcarrefour_onecarrefour_web%26redirect_uri%3Dhttps%253A%252F%252Fwww.carrefour.fr%252Flogin%252Fcheck%26response_type%3Dcode%26scope%3Dopenid%2520iam%2520register-aHR0cHM6Ly93d3cuY2FycmVmb3VyLmZyL21vbi1jb21wdGUvaW5zY3JpcHRpb24%253D&realm=%2FCarrefourConnect"
    USERNAME = "your_username"
    PASSWORD = "your_password"

    # arguments for requests
    # TODO: put in SECRETS
    url = "https://www.carrefour.fr/api/user/secured/loyalty/orders/receipts"
    params = {
        "loyaltyCardNumber": f"{config.LOYALTY_CARD_NUMBER}",
        "loyaltyCardType": "LOYALTY",
    }
    # headers = {
    #     "accept": "application/json, text/plain, */*",
    #     "accept-language": "fr,fr-FR;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    #     "priority": "u=1, i",
    #     "sec-ch-ua": '"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    #     "sec-ch-ua-mobile": "?0",
    #     "sec-ch-ua-platform": '"macOS"',
    #     "sec-fetch-dest": "empty",
    #     "sec-fetch-mode": "cors",
    #     "sec-fetch-site": "same-origin",
    #     "x-requested-with": "XMLHttpRequest",
    #     "referrer": "https://www.carrefour.fr/mon-compte/mes-achats/en-magasin",
    #     "referrer-policy": "strict-origin-when-cross-origin",
    # }

    HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        # "Priority": "u=1, i",
        # "Sec-Ch-Ua": '"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
        # "Sec-Ch-Ua-Mobile": "?0",
        # "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0",
        "X-Requested-With": "XMLHttpRequest",
        "Referrer": "https://www.carrefour.fr/mon-compte/mes-achats/en-magasin",
        "Referrer-policy": "strict-origin-when-cross-origin",
    }

    # List of User-Agents
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/120.0",
    ]

    # selected_user_agent = random.choice(user_agents)

    # # Include cookies if authentication is required (e.g., session cookies)
    # cookies = {
    #     "session_id": "your_session_cookie_here"  # Replace with actual session cookie [[5]]
    # }

    scraper = WebScraper(LOGIN_PAGE, USERNAME, PASSWORD)
    scraper.login()

    # Use the extracted cookies and User-Agent for API calls
    headers = HEADERS | {"User-Agent": scraper.get_user_agent()}

    data = WebScraper.fetch_requests_data(
        url, params, headers, scraper.cookies, proxies=None
    )

    scraper.end_session()
    print(data.text)
    print(data.json())
