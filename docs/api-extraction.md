---
noteId: "6a0fd680555511f19bb6f1faf66f1118"
tags: []

---

# API extraction & authentication

How raw receipts, Drive orders and loyalty (fidélité) operations are pulled from the
Carrefour portal. This is the only stage that needs credentials; everything downstream
runs on the exported files.

> ⚠️ The extracted files (under `data/`) contain personal data — loyalty card numbers,
> receipt details. `data/` is git-ignored and must never be committed. CI uses only the
> committed fixtures in `tests/fixtures/`.

## Why it's not a plain `requests` call

The Carrefour site is behind Cloudflare and uses `SameSite` cookies, so a bare HTTP
client can't authenticate. Two practical paths exist:

1. **Copy-as-cURL (recommended).** Log in normally in a browser (clearing Cloudflare
   Turnstile), open DevTools → Network, right-click a request → *Copy as cURL*. This
   captures the authenticated cookies. Save them to the file referenced by
   `COOKIES_FILE` (default `data/cookies.txt`). The cookies stay valid for the life of
   the browser session; run the extractor from the **same IP** used to load the site.
2. **Browser automation (fallback, deprecated).** `undetected_chromedriver` /
   SeleniumBase / Playwright can drive a real browser to harvest cookies — see
   [seleniumbase_extractor.py](../src/carrefour_receipts_api/seleniumbase_extractor.py)
   and [playwright_extractor.py](../src/carrefour_receipts_api/playwright_extractor.py)
   (install with the `scraping` extra). These are kept for reference but the cURL path is
   simpler and more reliable.

Once authenticated, the API responses are fetched with `curl` (subprocess) — chained GET
requests need no pause once the session is alive.

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
