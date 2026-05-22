# API extraction & authentication

How raw receipts, Drive orders and loyalty (fidélité) operations are pulled from the
Carrefour portal. This is the only stage that needs credentials; everything downstream
runs on the exported files.

> ⚠️ The extracted files (under `data/`) contain personal data — loyalty card numbers,
> receipt details. `data/` is git-ignored and must never be committed. CI uses only the
> committed fixtures in `tests/fixtures/`.

## Why it's not a plain `requests` call

The Carrefour site is behind Cloudflare. Two distinct walls:

1. **Getting the cookies** — Cloudflare Turnstile challenges the login page. The supported
   path is the **auth service** below (patched browser); two manual fallbacks also exist.
2. **Using the cookies** — Cloudflare binds the `cf_clearance` cookie to the **TLS
   fingerprint (JA3)** of the browser that solved the challenge. `requests`, `httpx` and
   plain `curl` all use OpenSSL, whose handshake doesn't match a browser, so they get a
   `403 cf-mitigated: challenge` *even with valid cookies*. The extractor therefore fetches
   with **[`curl_cffi`](https://github.com/lexiforest/curl_cffi)** (curl-impersonate /
   BoringSSL), reproducing a real browser's handshake. The impersonation target is
   `CARREFOUR_TLS_IMPERSONATE` (default `edge101`) and must match the login browser family.

## Auth service (browser login → cookies)

[auth_service/](../src/carrefour_receipts_api/auth_service/) is a small FastAPI app that
works like a browser-based OAuth login (à la Claude Code): it **opens the Carrefour login
portal in a real browser, you log in, and it retrieves the credential from the browser**
— except Carrefour isn't an OAuth provider, so the credential we keep is the **session
cookie jar**, not a token. (A cross-domain `localhost` callback can't read `carrefour.fr`
cookies, which is why we capture from the browser instead of a redirect callback.)

```bash
uv sync --extra api --extra scraping
uv run playwright install chromium     # once, for the browser flow
make auth-service                      # serves http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000> and pick:

| Endpoint | Flow |
| --- | --- |
| `POST /login/browser` | Pops a real browser at the login portal; when you reach your account page it captures the cookies automatically and writes `COOKIES_FILE`. Needs the `scraping` extra (Playwright). |
| `GET /login/redirect` | Redirects your current tab to the Carrefour login portal (manual path). |
| `POST /cookies` | Manual fallback: paste a `cookie:` header (from DevTools → Network) to save it. |
| `GET /status` | JSON — whether valid cookies are present. |

Cookies are written in the **Netscape format** that the extractor's `curl -b` calls
expect, at `config.COOKIES_FILE` (default `data/cookies.txt`). Configure the portal URLs
with `CARREFOUR_LOGIN_URL` / `CARREFOUR_ACCOUNT_URL`.

**Cloudflare Turnstile.** Turnstile detects ordinary Playwright through the Chrome
DevTools Protocol `Runtime.enable` leak, so the flow prefers **[patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)**
— a drop-in, CDP-leak-patched Playwright fork — when it's installed (`scraping` extra),
falling back to vanilla Playwright otherwise. It also drives a **real installed browser**
(auto-probes Chrome → Edge → bundled Chromium; force one with `BROWSER_CHANNEL`) and reuses
a **persistent profile** at `BROWSER_PROFILE_DIR` (default `data/browser_profile`,
git-ignored) so a once-passed challenge is remembered.

```bash
uv run patchright install chromium     # patched browser for the best Turnstile evasion
```

Turnstile also weighs IP reputation and behavioral signals, so even patched automation can
be challenged. When that happens, use the manual `POST /cookies` paste below — you log in
in your own normal browser (no automation at all), so it always works.

### Manual fallbacks (no service)

1. **Copy-as-cURL.** Log in in a browser (clearing Turnstile), DevTools → Network →
   right-click a request → *Copy as cURL*; save the cookies to `COOKIES_FILE`. Run the
   extractor from the **same IP** used to load the site.
2. **Browser automation (deprecated).** `undetected_chromedriver` / SeleniumBase /
   Playwright drivers in
   [seleniumbase_extractor.py](../src/carrefour_receipts_api/seleniumbase_extractor.py)
   and [playwright_extractor.py](../src/carrefour_receipts_api/playwright_extractor.py)
   (install with the `scraping` extra). Superseded by the auth service.

## Modules

- [login.py](../src/carrefour_receipts_api/login.py) — loads credentials from the YAML
  secrets file (`SECRETS_FILE`, default `data/secrets.yml`) and parses the cookie jar.
- [user_api_extractor.py](../src/carrefour_receipts_api/user_api_extractor.py) — the
  extractors. A small factory builds the right one per record type:
  - `CarrefourReceiptExtractor` — in-store receipts,
  - `CarrefourOrderExtractor` — online (Drive) orders,
  - `CarrefourLoyaltyExtractor` — monthly loyalty operations.

  Each handles pagination (`scrollHash`), fetches the list of IDs, then fetches details
  per ID and writes JSON into `data/{YYYYMMDD}/`. Logging is structured (structlog) — set
  `LOG_JSON=true` for machine-readable output.

> **Loyalty's rolling 1-year window.** The loyalty endpoint only returns operations from
> roughly the last year, so each extract is a moving snapshot, not the full history. The ELT
> loader absorbs this: `loyalty` is loaded with dlt `merge` on a synthetic per-line key, so
> DuckDB **accumulates** the union across runs. A fresh ~1-year extract therefore never
> erases the months you captured earlier (and re-running never duplicates rows). See the
> loyalty resource in [elt/load.py](../src/carrefour_receipts_api/elt/load.py).

## Running it

```bash
uv sync --extra scraping            # only if you need the browser fallbacks
# put cookies in data/cookies.txt and credentials in data/secrets.yml, then:
uv run python -m carrefour_receipts_api.user_api_extractor
```

## Output → next stage

The JSON receipts and the loyalty CSV are the input to the ELT loader. See
[development.md](development.md) for loading them into DuckDB and
[architecture.md](architecture.md) for the overall flow.

## Data shapes

- **Receipts**: `id` (`gln_dateKey_receiptNumber`), `dateKey`, store, totals, plus nested
  arrays — products, VATs, payment splits, coupons — which dlt unnests into child tables.
- **Loyalty**: one row per operation — `date`, `itemLabel`, `earned`, `burned`, `itemRd`
  (item discount), `loyaltyOperation`.
