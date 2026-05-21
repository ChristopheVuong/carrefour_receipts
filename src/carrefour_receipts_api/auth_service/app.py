"""FastAPI auth service — Carrefour browser login + cookie capture.

Endpoints:
  - ``GET  /``                landing page (status + buttons)
  - ``GET  /status``          JSON: are valid cookies present?
  - ``POST /login/browser``   pop a real browser at the login portal, capture cookies
                              when login completes (needs the ``scraping`` extra)
  - ``GET  /login/redirect``  redirect the current tab to the Carrefour login portal
                              (manual path — log in, then paste the cookie header below)
  - ``POST /cookies``         manual fallback: paste a ``Cookie:`` header to save it

Run: ``make auth-service`` or ``uvicorn carrefour_receipts_api.auth_service.app:app``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from carrefour_receipts_api import config
from carrefour_receipts_api.auth_service.cookies import (
    cookie_header_to_netscape,
    count_cookies,
    write_cookies_file,
)

app = FastAPI(title="Carrefour Auth Service")


def _cookie_status() -> dict[str, object]:
    path = Path(config.COOKIES_FILE)
    if not path.exists():
        return {"cookies_present": False, "count": 0, "cookies_file": str(path)}
    text = path.read_text(encoding="utf-8")
    count = count_cookies(text)
    return {"cookies_present": count > 0, "count": count, "cookies_file": str(path)}


_PAGE = """\
<!doctype html><html><head><meta charset="utf-8">
<title>Carrefour Auth</title>
<style>
 body {{ font-family: system-ui, sans-serif; max-width: 640px; margin: 3rem auto; padding: 0 1rem; }}
 .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0; }}
 button {{ font-size: 1rem; padding: .5rem 1rem; cursor: pointer; }}
 textarea {{ width: 100%; height: 5rem; }}
 code {{ background: #f4f4f4; padding: .1rem .3rem; border-radius: 4px; }}
 .ok {{ color: #137333; }} .no {{ color: #a50e0e; }}
</style></head><body>
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
</body></html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    status = _cookie_status()
    present = status["cookies_present"]
    return HTMLResponse(
        _PAGE.format(
            cls="ok" if present else "no",
            status_text=(f"{status['count']} cookies saved" if present else "no cookies yet"),
            cookies_file=status["cookies_file"],
        )
    )


@app.get("/status")
def status() -> JSONResponse:
    return JSONResponse(_cookie_status())


@app.get("/login/redirect")
def login_redirect() -> RedirectResponse:
    """Redirect the user's browser to the Carrefour login portal."""
    return RedirectResponse(config.CARREFOUR_LOGIN_URL)


@app.post("/login/browser")
async def login_browser() -> JSONResponse:
    """Pop a browser at the login portal and capture cookies on completion."""
    from carrefour_receipts_api.auth_service.browser import capture_cookies_via_browser

    try:
        count = await capture_cookies_via_browser()
    except RuntimeError as exc:  # Playwright missing
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=501)
    except TimeoutError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=408)
    return JSONResponse({"ok": True, "count": count, **_cookie_status()})


@app.post("/cookies")
def save_cookies(cookie_header: str = Form(...)) -> JSONResponse:
    """Save cookies pasted as a raw ``Cookie:`` header (manual fallback)."""
    try:
        netscape = cookie_header_to_netscape(cookie_header)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    count = write_cookies_file(netscape, config.COOKIES_FILE)
    return JSONResponse({"ok": True, "count": count, **_cookie_status()})


def main() -> None:
    """Run the service with uvicorn (``make auth-service``)."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
