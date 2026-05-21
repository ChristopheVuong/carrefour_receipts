"""
Login and cookies retrieval based on SeleniumBase
Release after treatment.
"""

from http.cookiejar import CookieJar, Cookie
import logging
import random
import time
from typing import Dict, Any, Optional

import requests
from requests.cookies import create_cookie
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import undetected_chromedriver as uc
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


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



