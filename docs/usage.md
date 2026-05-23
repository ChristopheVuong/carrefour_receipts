# Usage guide

End-to-end walkthrough: from a fresh clone to a running dashboard, then keeping
your data up to date over time. For the "why" behind each step see
[architecture.md](architecture.md); for troubleshooting auth see
[api-extraction.md](api-extraction.md).

---

## 1. One-time setup

```bash
git clone <repo>
cd carrefour_receipts

# Install all extras needed for extraction + ELT + dbt + dashboard
uv sync --extra elt --extra analysis --extra dashboard --extra scraping --extra api

cp .env.example .env
```

You can set your card numbers in `.env`:

```ini
LOYALTY_CARD_NUMBER=<your fidélité card number>
PASS_CARD_NUMBER=<your Pass Mastercard number, if any>
```

…but you don't have to — the **auth service (step 2)** captures them for you (read from the
my-cards JSON on login, or entered in its form) and stores them in `data/secrets.yml`.
`.env` always overrides that file if both are set.

Everything else has sensible defaults (see [development.md](development.md#environment-variables)).
The `data/` directory is git-ignored; all personal data stays there.

---

## 2. Get cookies from Carrefour (first time and when they expire)

The Carrefour portal uses Cloudflare Turnstile — you must log in via a real browser
once. The **auth service** automates this:

```bash
make auth-service   # starts FastAPI on http://localhost:8000
```

Open `http://localhost:8000` and click **Open browser & capture cookies**. The service
launches a Playwright/patchright browser; you log in (clearing Turnstile), and once you
reach your account page it:

1. writes `data/cookies.txt`
2. reads your **loyalty / Pass card numbers** from the my-cards endpoint and saves them to `data/secrets.yml`
3. redirects your tab to a **confirmation page** showing both card numbers and the cookie count

If a number is missing on the confirmation page, click *Back* and fill in the
*Loyalty / fidélité card* form manually.

> The service keeps running after a successful login — stop it with `Ctrl+C`.

Cookies live for several weeks. When requests start returning 403, repeat this step.
See [api-extraction.md](api-extraction.md) for details on the Cloudflare bypass.

---

## 3. Extract your data

Pick the record type with `--type` (receipts are the default):

```bash
uv run python -m carrefour_receipts_api.user_api_extractor --type receipt
uv run python -m carrefour_receipts_api.user_api_extractor --type loyalty_operation
uv run python -m carrefour_receipts_api.user_api_extractor --type order   # Drive orders
```

This writes JSON under a **dated folder per extraction run**:
- `data/{YYYYMMDD}/…_receipts_scroll_N.json` — receipt list pages
- `data/{YYYYMMDD}/…_receipt_{id}_details.json` — individual receipt details
- `data/{YYYYMMDD}/…_loyalty_operations_all.json` — one document **per month**, each
  carrying a `history` array of loyalty line items
- `data/{YYYYMMDD}/…_order_{id}_details.json` — individual Drive order details

All three record types are plain JSON — there is no CSV intermediate.

### Pointing the loader at your files

Each run creates a **new dated folder**, but you don't chase the date in `.env` — point
both sources at `data` **once**:

```ini
RECEIPTS_SOURCE_DIR=data          # parent dir, NOT a single dated subfolder
LOYALTY_SOURCE_DIR=data           # loyalty JSON co-locates under data/{YYYYMMDD}/
ORDERS_SOURCE_DIR=data            # Drive order JSON co-locates there too
```

Each resource scans its dir recursively (`rglob("*.json")`) and picks its own docs
(receipts have an `id`; loyalty months have a `history` array; orders have an
`attributes.productList`), so they pick up **every** dated subfolder from **every** run
automatically. Receipts `merge` on `id`, loyalty on the month `_id`, orders on
`order_number` — accumulating history in DuckDB across runs. So after the first time,
step 3 → step 4 needs no `.env` change.

---

## 4. Load into DuckDB and build the data mart

```bash
make build
# = dlt load (receipts + loyalty) → raw.* then dbt build (staging → marts → analytics)
```

Or step by step:

```bash
make elt    # dlt only  →  raw.*
make dbt    # dbt only  →  star schema + analytics marts
```

The first full build takes ~10 s on the fixtures; real data takes longer depending on
receipt count (categorization fuzzy-matches every distinct product label).

---

## 5. Explore the data mart

```bash
# Interactive dbt documentation site (models, lineage, column descriptions, tests)
make docs-dbt
# = cd transform && dbt docs generate && dbt docs serve  →  http://localhost:8080
```

Or query DuckDB directly:

```bash
uv run python -c "
import duckdb
con = duckdb.connect('carrefour.duckdb')
print(con.execute('select year_month, total_paid from main.mart_monthly_spend order by 1 desc limit 6').df())
"
```

---

## 6. Launch the dashboard

```bash
make dashboard   # →  http://localhost:8501
```

Sections: headline KPIs, monthly spend + rolling average, category breakdown,
product price trends, quantity series. All filterable by year / month / category /
**channel** (All / store / Drive — "All" sums the two).

See [dashboard.md](dashboard.md) for the Docker variant.

---

## 7. Periodic refresh (monthly or quarterly)

Run steps **2 → 3 → 4** again. Key points:

| Data | Behaviour on re-run |
|---|---|
| **Receipts** | Merged on `id` — updated in place, new ones added. Running twice = same result. |
| **Loyalty** | Merged on a synthetic key — DuckDB accumulates across loads. **Don't delete `carrefour.duckdb` between runs** (except a deliberate full rebuild). |

> Loyalty's API only returns the past ~12 months, so **re-extract at least once a year** to
> keep the history continuous; older months already in DuckDB are preserved either way.
> Receipts are unaffected (they accumulate regardless).

Typical refresh:

```bash
make auth-service          # if cookies expired
uv run python -m carrefour_receipts_api.user_api_extractor --type receipt
uv run python -m carrefour_receipts_api.user_api_extractor --type loyalty_operation
uv run python -m carrefour_receipts_api.user_api_extractor --type order
make build                 # incremental load (recursive glob + merge) + dbt rebuild
make dashboard
```

No `.env` change between runs: with `RECEIPTS_SOURCE_DIR=data` / `LOYALTY_SOURCE_DIR=data`
the recursive globs pick up the new dated folder, and the merge keys deduplicate against
what's already in DuckDB.

---

## 8. Full rebuild from scratch

```bash
make clean     # removes carrefour.duckdb, dbt artifacts and dlt pipeline state
# point .env at ALL your archived extracts (or a merged source dir)
make build
```

If you have multiple extract directories (e.g. `data/20240601`, `data/20250101`),
set `RECEIPTS_SOURCE_DIR` / `LOYALTY_SOURCE_DIR` to a parent that contains them all — both
resources scan recursively (`rglob("*.json")`). The merge keys (receipt `id`, loyalty
month `_id`) deduplicate overlapping documents automatically.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Extractor returns 403 | Cookies expired | Re-run `make auth-service` → click *Open browser & capture cookies* |
| `dbt build` fails on `stg_loyalty` | No loyalty JSON loaded (`raw.loyalty` absent) | Run the loyalty extraction (`--type loyalty_operation`), check `LOYALTY_SOURCE_DIR`, then `make elt` |
| Dashboard shows "marts not found" | `dbt build` not run yet | `make build` |
| Duplicate loyalty rows in DuckDB | Unlikely; if seen after a schema change to `loyalty_operation_id` | `make clean && make build` with all archived files |
| `make elt` fails with `Catalog Error: Table … does not exist! Did you mean raw_staging.…?` | A previous dlt load was interrupted, leaving its schema out of sync with DuckDB | `make clean && make build` (clears the dlt pipeline state too) |
