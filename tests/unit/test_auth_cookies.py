"""Unit tests for the auth-service cookie helpers (no browser, no network).

These pin the contract the extractor relies on: cookies must be written in the
Netscape format that ``curl -b`` reads, from both the Playwright-capture path and the
manual ``Cookie:`` header paste.
"""

import pytest

from carrefour_receipts_api.auth_service.cookies import (
    cookie_header_to_netscape,
    count_cookies,
    playwright_cookies_to_netscape,
    write_cookies_file,
)


@pytest.mark.fast
def test_playwright_cookies_render_netscape_rows():
    cookies = [
        {
            "name": "sid",
            "value": "abc",
            "domain": ".carrefour.fr",
            "path": "/",
            "secure": True,
            "expires": 1893456000,
        },
        {
            "name": "sess",
            "value": "xyz",
            "domain": "www.carrefour.fr",
            "path": "/",
            "secure": False,
            "expires": -1,
        },  # session cookie -> 0
    ]
    text = playwright_cookies_to_netscape(cookies)
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(lines) == 2
    # 7 tab-separated columns, includeSubdomains flag derived from leading dot.
    sid = lines[0].split("\t")
    assert sid == [".carrefour.fr", "TRUE", "/", "TRUE", "1893456000", "sid", "abc"]
    sess = lines[1].split("\t")
    assert sess[1] == "FALSE"  # no leading dot
    assert sess[3] == "FALSE"  # not secure
    assert sess[4] == "0"  # session expiry normalized


@pytest.mark.fast
@pytest.mark.parametrize(
    "header",
    [
        "foo=bar; baz=qux",
        "cookie: foo=bar; baz=qux",
        "  foo=bar ;  baz=qux ; ",
    ],
)
def test_cookie_header_parses_pairs(header):
    text = cookie_header_to_netscape(header)
    rows = [line.split("\t") for line in text.splitlines() if line and not line.startswith("#")]
    names = {r[5]: r[6] for r in rows}
    assert names == {"foo": "bar", "baz": "qux"}
    assert all(r[0] == ".carrefour.fr" and r[3] == "TRUE" for r in rows)


@pytest.mark.fast
def test_cookie_header_rejects_empty():
    with pytest.raises(ValueError):
        cookie_header_to_netscape("   ;  ; ")


@pytest.mark.fast
def test_write_cookies_file_roundtrip(tmp_path):
    target = tmp_path / "nested" / "cookies.txt"
    text = cookie_header_to_netscape("a=1; b=2; c=3")
    count = write_cookies_file(text, target)
    assert count == 3
    assert target.exists()
    assert count_cookies(target.read_text()) == 3
