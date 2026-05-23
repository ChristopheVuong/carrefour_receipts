"""Browser-driven Carrefour login + cookie capture.

Opens a real (headed) browser at the Carrefour login portal, waits for the user to
authenticate, and once they reach the account area harvests the session cookies and
writes them to the cookie file. This is the "token retrieval from the browser" step,
analogous to an OAuth browser login — except the credential we keep is the cookie jar.

Cloudflare Turnstile detects ordinary Playwright via the Chrome DevTools Protocol
``Runtime.enable`` leak, so we prefer **patchright** (a drop-in, CDP-leak-patched
Playwright) when installed and fall back to vanilla Playwright otherwise. The browser
backend is imported lazily so the rest of the auth service (and type-checking) works
without the optional ``scraping`` extra installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from carrefour_receipts_api import config
from carrefour_receipts_api.auth_service.cookies import (
    playwright_cookies_to_netscape,
    write_cookies_file,
)
from carrefour_receipts_api.logging_config import get_logger
from carrefour_receipts_api.secrets_store import write_secrets

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Playwright

logger = get_logger(__name__)

# Vanilla-Playwright stealth tweaks. NOT applied with patchright: that backend patches
# these itself, and the automation arg is *itself* a Cloudflare detection signal.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_STEALTH_ARGS = ["--disable-blink-features=AutomationControlled"]
_STEALTH_INIT = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"


def _import_backend() -> tuple[Any, str]:
    """Return ``(async_playwright, backend_name)``, preferring patchright.

    patchright is a drop-in Playwright fork that hides the CDP ``Runtime.enable`` leak
    Cloudflare Turnstile checks; if it isn't installed we fall back to vanilla Playwright.
    """
    try:
        from patchright.async_api import async_playwright as patchright_apw

        return patchright_apw, "patchright"
    except ImportError:
        pass
    try:
        from playwright.async_api import async_playwright as playwright_apw

        return playwright_apw, "playwright"
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "A browser backend is required for the browser login flow. Install one with: "
            "uv sync --extra api --extra scraping && uv run patchright install chrome "
            "(or 'uv run playwright install chromium')."
        ) from exc


async def _launch_context(p: Playwright, profile_dir: str, *, patched: bool) -> BrowserContext:
    """Open a headed, persistent browser context tuned to survive Turnstile.

    Drives a real installed browser — Chrome, then Edge — whose fingerprint is far more
    legitimate than bundled Chromium, falling back to Chromium only if none are present.
    ``config.BROWSER_CHANNEL`` forces a specific channel. The persistent profile means a
    once-passed Turnstile is remembered.

    With ``patched`` (patchright) we keep the launch config minimal: patchright's defaults
    are the stealthiest, and extra args/UA overrides would re-introduce detectable signals.
    """
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {"headless": False}
    if not patched:
        kwargs["args"] = _STEALTH_ARGS
        kwargs["user_agent"] = _USER_AGENT
    # Forced channel, else auto-probe real browsers; final None = bundled Chromium.
    channels: list[str | None] = (
        [config.BROWSER_CHANNEL] if config.BROWSER_CHANNEL else ["chrome", "msedge", None]
    )
    context = None
    for channel in channels:
        try:
            context = await p.chromium.launch_persistent_context(
                profile_dir, channel=channel, **kwargs
            )
            logger.info("browser_channel", channel=channel or "chromium")
            break
        except Exception as exc:  # noqa: BLE001 - channel not installed -> try next
            logger.info(
                "browser_channel_unavailable", channel=channel or "chromium", reason=str(exc)
            )
    if context is None:
        raise RuntimeError(
            "Could not launch any browser. Install Chrome/Edge, or run "
            "'uv run playwright install chromium'."
        )
    if not patched:
        await context.add_init_script(_STEALTH_INIT)
    return context


# Every Carte Carrefour (LOYALTY) barcode shares the prefix "913572" (per Carrefour's own
# documentation). The my-cards endpoint returns the number WITHOUT it (e.g. "0000005422294"),
# but receipts and the loyalty API use the full barcode ("9135720000005422294"). The PASS
# Mastercard number is already complete and is left untouched.
_LOYALTY_PREFIX = "913572"


def _normalize_loyalty_number(number: str) -> str:
    """Prepend the Carte Carrefour prefix to a LOYALTY number that lacks it (idempotent)."""
    return number if number.startswith(_LOYALTY_PREFIX) else _LOYALTY_PREFIX + number


def _card_from(node: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(number, type)`` if ``node`` looks like a loyalty card, else ``None``.

    Tolerant of the two known schemas: ``my-cards`` (``loyaltyCardNumber`` +
    ``loyaltyCardType``) and ``/api/me`` (``number`` + ``type``).
    """
    number = node.get("loyaltyCardNumber") or node.get("number")
    ctype = node.get("loyaltyCardType") or node.get("type")
    if number and isinstance(ctype, str):
        return str(number), ctype
    return None


def parse_card_numbers(payload: Any) -> dict[str, str | None]:
    """Extract the loyalty / Pass card numbers from the my-cards JSON.

    Walks the payload (``attributes`` is a list of cards) and classifies each card by
    type: ``PASS`` → Pass Mastercard, anything else (``LOYALTY``) → loyalty card. The
    LOYALTY number is normalized to its full barcode form (see ``_normalize_loyalty_number``).
    The first number seen per type wins. Best-effort: a missing card stays ``None``.
    """
    result: dict[str, str | None] = {"loyaltyCardNumber": None, "passCardNumber": None}

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            card = _card_from(node)
            if card is not None:
                number, ctype = card
                if "PASS" in ctype.upper():
                    result["passCardNumber"] = result["passCardNumber"] or number
                else:
                    result["loyaltyCardNumber"] = result[
                        "loyaltyCardNumber"
                    ] or _normalize_loyalty_number(number)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return result


async def fetch_card_numbers(context: BrowserContext) -> dict[str, str | None]:
    """Query the authenticated my-cards endpoint and parse the card numbers.

    Uses the browser context's request API so the session cookies are sent.
    """
    response = await context.request.get(config.CARREFOUR_CARDS_URL)
    return parse_card_numbers(await response.json())


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

    Returns the number of cookies captured. Raises ``RuntimeError`` if no browser
    backend is installed, or ``TimeoutError`` if login wasn't completed in time.
    """
    login_url = login_url or config.CARREFOUR_LOGIN_URL
    success_url = success_url or config.CARREFOUR_ACCOUNT_URL
    cookies_file = cookies_file or config.COOKIES_FILE

    async_playwright, backend = _import_backend()
    logger.info(
        "browser_login_start", login_url=login_url, success_url=success_url, backend=backend
    )

    async with async_playwright() as p:
        context = await _launch_context(
            p, config.BROWSER_PROFILE_DIR, patched=(backend == "patchright")
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(login_url)

        try:
            # Wait until the user lands on the account area (login complete).
            await page.wait_for_url(f"{success_url}**", timeout=timeout_s * 1000)
        except Exception as exc:  # noqa: BLE001 - surface as a clean timeout
            await context.close()
            logger.error("browser_login_timeout", error=str(exc))
            raise TimeoutError(
                "Login was not completed in time (never reached the account page)."
            ) from exc

        # Best-effort: harvest the loyalty / Pass card numbers from the my-cards endpoint.
        # A failure here must never break cookie capture (the primary job).
        try:
            cards = await fetch_card_numbers(context)
            write_secrets(
                config.SECRETS_FILE,
                loyaltyCardNumber=cards.get("loyaltyCardNumber"),
                passCardNumber=cards.get("passCardNumber"),
            )
            logger.info(
                "loyalty_cards_captured",
                loyalty_present=bool(cards.get("loyaltyCardNumber")),
                pass_present=bool(cards.get("passCardNumber")),
                secrets_file=config.SECRETS_FILE,
            )
        except Exception as exc:  # noqa: BLE001 - capture is best-effort
            logger.warning("loyalty_capture_failed", error=str(exc))

        cookies = await context.cookies()
        await context.close()

    netscape = playwright_cookies_to_netscape([dict(c) for c in cookies])
    count = write_cookies_file(netscape, cookies_file)
    logger.info("browser_login_captured", cookie_count=count, cookies_file=cookies_file)
    return count
