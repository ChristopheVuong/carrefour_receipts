"""FastAPI auth service — Carrefour browser login + cookie capture.

Endpoints:
  - ``GET  /``                landing page (status + buttons)
  - ``GET  /status``          JSON: are valid cookies present?
  - ``POST /login/browser``   pop a real browser at the login portal, capture cookies
                              (and scrape the loyalty/Pass card numbers) on completion
                              (needs the ``scraping`` extra)
  - ``GET  /login/redirect``  redirect the current tab to the Carrefour login portal
                              (manual path — log in, then paste the cookie header below)
  - ``POST /cookies``         manual fallback: paste a ``Cookie:`` header to save it
  - ``POST /account``         save the loyalty / Pass card numbers (manual fallback)

Run: ``make auth-service`` or ``uvicorn carrefour_receipts_api.auth_service.app:app``.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from carrefour_receipts_api import config
from carrefour_receipts_api.auth_service.cookies import (
    cookie_header_to_netscape,
    count_cookies,
    write_cookies_file,
)
from carrefour_receipts_api.secrets_store import read_secrets, write_secrets

app = FastAPI(title="Carrefour Auth Service")


def _cookie_status() -> dict[str, object]:
    path = Path(config.COOKIES_FILE)
    if not path.exists():
        return {"cookies_present": False, "count": 0, "cookies_file": str(path)}
    text = path.read_text(encoding="utf-8")
    count = count_cookies(text)
    return {"cookies_present": count > 0, "count": count, "cookies_file": str(path)}


def _account_status() -> dict[str, object]:
    """Resolve the card numbers live (env override > secrets.yml) for display/JSON.

    Reads the file fresh rather than via ``config`` (which is frozen at import), so the
    UI reflects a number the browser flow just scraped.
    """
    secrets = read_secrets(config.SECRETS_FILE)
    loyalty = os.getenv("LOYALTY_CARD_NUMBER") or secrets.get("loyaltyCardNumber", "")
    pass_ = os.getenv("PASS_CARD_NUMBER") or secrets.get("passCardNumber", "")
    return {
        "loyalty_present": bool(loyalty),
        "pass_present": bool(pass_),
        "loyalty_card_number": loyalty,
        "pass_card_number": pass_,
        "secrets_file": config.SECRETS_FILE,
    }


_STYLE = """\
 body {{ font-family: system-ui, sans-serif; max-width: 640px; margin: 3rem auto; padding: 0 1rem; }}
 .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0; }}
 button {{ font-size: 1rem; padding: .5rem 1rem; cursor: pointer; }}
 textarea {{ width: 100%; height: 5rem; }}
 input[type=text] {{ width: 100%; padding: .35rem; margin: .15rem 0 .6rem; }}
 label {{ font-size: .9rem; }}
 code {{ background: #f4f4f4; padding: .1rem .3rem; border-radius: 4px; }}
 .ok {{ color: #137333; }} .no {{ color: #a50e0e; }}
 .success-banner {{ background: #e6f4ea; border: 1px solid #137333; border-radius: 8px;
                    padding: 1.25rem 1.5rem; margin: 1rem 0; }}
 .cred {{ font-family: monospace; font-size: 1rem; background: #f4f4f4;
           padding: .2rem .5rem; border-radius: 4px; word-break: break-all; }}
"""

_PAGE = """\
<!doctype html><html><head><meta charset="utf-8">
<title>Carrefour Auth</title>
<style>{style}</style></head><body>
<h1>🧾 Carrefour Auth</h1>
<p>Status: <strong class="{cls}">{status_text}</strong> &middot; <code>{cookies_file}</code></p>

<div class="card">
 <h3>1. Browser login (recommended)</h3>
 <p>Opens a real browser at the Carrefour login portal. Log in there (clearing
    Cloudflare Turnstile); cookies are captured automatically when you reach your
    account page.</p>
 <form method="post" action="/login/browser">
   <button type="submit">Open browser &amp; capture cookies</button>
 </form>
</div>

<div class="card">
 <h3>2. Manual</h3>
 <p><a href="/login/redirect" target="_blank">Open the Carrefour login portal</a> in a
    new tab, log in, then from DevTools &rarr; Network copy a request's
    <code>cookie:</code> header and paste it here:</p>
 <form method="post" action="/cookies">
   <textarea name="cookie_header" placeholder="cookie: foo=bar; baz=qux"></textarea>
   <button type="submit">Save cookies</button>
 </form>
</div>

<div class="card">
 <h3>3. Loyalty / fidélité card</h3>
 <p>Captured automatically from your account page during browser login, or set them
    here. Used as the receipt/loyalty API parameters, saved to <code>{secrets_file}</code>
    (<code>.env</code> still overrides).</p>
 <p>Loyalty: <strong class="{loyalty_cls}">{loyalty_text}</strong> &middot;
    Pass: <strong class="{pass_cls}">{pass_text}</strong></p>
 <form method="post" action="/account">
   <label>Loyalty card number<input type="text" name="loyalty_card_number" value="{loyalty_value}"></label>
   <label>Pass card number<input type="text" name="pass_card_number" value="{pass_value}"></label>
   <button type="submit">Save card numbers</button>
 </form>
</div>
</body></html>
"""

_SUCCESS_PAGE = """\
<!doctype html><html><head><meta charset="utf-8">
<title>Carrefour Auth — Login OK</title>
<style>{style}</style></head><body>
<h1>🧾 Carrefour Auth</h1>

<div class="success-banner">
 <strong class="ok">&#10003; Login successful</strong> &mdash; {count} cookies saved
 to <code>{cookies_file}</code>.
</div>

<div class="card">
 <h3>Loyalty / fidélité card numbers</h3>
 <table style="border-collapse:collapse;width:100%">
  <tr>
   <td style="padding:.4rem .6rem;width:40%;color:#555">Loyalty (Carte Carrefour)</td>
   <td style="padding:.4rem .6rem"><span class="cred {loyalty_cls}">{loyalty_text}</span></td>
  </tr>
  <tr>
   <td style="padding:.4rem .6rem;color:#555">Pass Mastercard</td>
   <td style="padding:.4rem .6rem"><span class="cred {pass_cls}">{pass_text}</span></td>
  </tr>
 </table>
 <p style="margin:.75rem 0 0;font-size:.85rem;color:#555">
  Saved to <code>{secrets_file}</code>. You can now close this tab and run the extractor.
 </p>
</div>

<p><a href="/">&larr; Back to main page</a></p>
</body></html>
"""


def _render_index() -> HTMLResponse:
    status = _cookie_status()
    present = status["cookies_present"]
    account = _account_status()
    return HTMLResponse(
        _PAGE.format(
            style=_STYLE,
            cls="ok" if present else "no",
            status_text=(f"{status['count']} cookies saved" if present else "no cookies yet"),
            cookies_file=status["cookies_file"],
            secrets_file=account["secrets_file"],
            loyalty_cls="ok" if account["loyalty_present"] else "no",
            loyalty_text=(account["loyalty_card_number"] or "not set"),
            pass_cls="ok" if account["pass_present"] else "no",
            pass_text=(account["pass_card_number"] or "not set"),
            loyalty_value=account["loyalty_card_number"],
            pass_value=account["pass_card_number"],
        )
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return _render_index()


@app.get("/status")
def status() -> JSONResponse:
    return JSONResponse(_cookie_status())


@app.get("/login/redirect")
def login_redirect() -> RedirectResponse:
    """Redirect the user's browser to the Carrefour login portal."""
    return RedirectResponse(config.CARREFOUR_LOGIN_URL)


@app.post("/login/browser", response_class=HTMLResponse)
async def login_browser() -> HTMLResponse:
    """Pop a browser at the login portal and capture cookies on completion."""
    from carrefour_receipts_api.auth_service.browser import capture_cookies_via_browser

    try:
        count = await capture_cookies_via_browser()
    except RuntimeError as exc:  # Playwright missing
        return HTMLResponse(f"<pre>Error: {exc}</pre>", status_code=501)
    except TimeoutError as exc:
        return HTMLResponse(f"<pre>Timeout: {exc}</pre>", status_code=408)
    account = _account_status()
    cookie_status = _cookie_status()
    return HTMLResponse(
        _SUCCESS_PAGE.format(
            style=_STYLE,
            count=count,
            cookies_file=cookie_status["cookies_file"],
            secrets_file=account["secrets_file"],
            loyalty_cls="ok" if account["loyalty_present"] else "no",
            loyalty_text=(account["loyalty_card_number"] or "not captured — enter below"),
            pass_cls="ok" if account["pass_present"] else "no",
            pass_text=(account["pass_card_number"] or "not captured — enter below"),
        )
    )


@app.post("/cookies")
def save_cookies(cookie_header: str = Form(...)) -> JSONResponse:
    """Save cookies pasted as a raw ``Cookie:`` header (manual fallback)."""
    try:
        netscape = cookie_header_to_netscape(cookie_header)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    count = write_cookies_file(netscape, config.COOKIES_FILE)
    return JSONResponse({"ok": True, "count": count, **_cookie_status()})


@app.post("/account")
def save_account(
    loyalty_card_number: str = Form(""),
    pass_card_number: str = Form(""),
) -> JSONResponse:
    """Save the loyalty / Pass card numbers to the secrets file (manual fallback).

    Empty fields are ignored, so submitting one number never wipes the other.
    """
    write_secrets(
        config.SECRETS_FILE,
        loyaltyCardNumber=loyalty_card_number,
        passCardNumber=pass_card_number,
    )
    return JSONResponse({"ok": True, **_account_status()})


def main() -> None:
    """Run the service with uvicorn (``make auth-service``)."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
