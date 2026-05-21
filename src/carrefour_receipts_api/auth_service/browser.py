"""Browser-driven Carrefour login + cookie capture (Playwright).

Opens a real (headed) browser at the Carrefour login portal, waits for the user to
authenticate, and once they reach the account area harvests the session cookies and
writes them to the cookie file. This is the "token retrieval from the browser" step,
analogous to an OAuth browser login — except the credential we keep is the cookie jar.

Playwright is imported lazily so the rest of the auth service (and type-checking)
works without the optional ``scraping`` extra installed.
"""

from __future__ import annotations

from carrefour_receipts_api import config
from carrefour_receipts_api.auth_service.cookies import (
    playwright_cookies_to_netscape,
    write_cookies_file,
)
from carrefour_receipts_api.logging_config import get_logger

logger = get_logger(__name__)


async def capture_cookies_via_browser(
    login_url: str | None = None,
    success_url: str | None = None,
    cookies_file: str | None = None,
    timeout_s: float = 300.0,
) -> int:
    """Open the login portal, wait for login, and save the session cookies.

    Args:
        login_url: Carrefour login page (default ``config.CARREFOUR_LOGIN_URL``).
        success_url: URL prefix that signals a completed login — when the browser
            reaches it we capture (default ``config.CARREFOUR_ACCOUNT_URL``).
        cookies_file: where to write the Netscape cookie file (default
            ``config.COOKIES_FILE``).
        timeout_s: how long to wait for the user to finish logging in.

    Returns the number of cookies captured. Raises ``RuntimeError`` if Playwright is
    not installed, or ``TimeoutError`` if login wasn't completed in time.
    """
    login_url = login_url or config.CARREFOUR_LOGIN_URL
    success_url = success_url or config.CARREFOUR_ACCOUNT_URL
    cookies_file = cookies_file or config.COOKIES_FILE

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "Playwright is required for the browser login flow. "
            "Install it with: uv sync --extra api --extra scraping "
            "&& uv run playwright install chromium"
        ) from exc

    logger.info("browser_login_start", login_url=login_url, success_url=success_url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(login_url)

        try:
            # Wait until the user lands on the account area (login complete).
            await page.wait_for_url(f"{success_url}**", timeout=timeout_s * 1000)
        except Exception as exc:  # noqa: BLE001 - surface as a clean timeout
            await browser.close()
            logger.error("browser_login_timeout", error=str(exc))
            raise TimeoutError(
                "Login was not completed in time (never reached the account page)."
            ) from exc

        cookies = await context.cookies()
        await browser.close()

    count = write_cookies_file(playwright_cookies_to_netscape(cookies), cookies_file)
    logger.info("browser_login_captured", cookie_count=count, cookies_file=cookies_file)
    return count
