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

Edit `.env` — the minimum required fields:

```ini
LOYALTY_CARD_NUMBER=<your fidélité card number>
PASS_CARD_NUMBER=<your Pass Mastercard number, if any>
```

Everything else has sensible defaults (see [development.md](development.md#environment-variables)).
The `data/` directory is git-ignored; all personal data stays there.

---

## 2. Get cookies from Carrefour (first time and when they expire)

The Carrefour portal uses Cloudflare Turnstile — you must log in via a real browser
once. The **auth service** automates this:

```bash
make auth-service   # starts FastAPI on http://localhost:8000
```

Open `http://localhost:8000/docs` in your browser and call `POST /login` with your
Carrefour credentials. The service launches a Playwright/patchright browser, completes
the login (including Turnstile), writes `data/cookies.txt`, and returns
`{"status": "ok"}`.

> The service keeps running after a successful login — stop it with `Ctrl+C`.

Cookies live for several weeks. When requests start returning 403, repeat this step.
See [api-extraction.md](api-extraction.md) for details on the Cloudflare bypass.

---

## 3. Extract your data

```bash
uv run python -m carrefour_receipts_api.user_api_extractor
```

This paginates the receipts API and the monthly loyalty endpoint, writing:
- `data/{YYYYMMDD}/…_receipts_scroll_N.json` — receipt list pages (one **dated folder
  per extraction run**)
- `data/{YYYYMMDD}/…_receipt_{id}_details.json` — individual receipt details
- `data/{record_type}_ids.csv` — the loyalty/receipt line CSVs (a **fixed, non-dated**
  path, appended and deduplicated across runs)

### Pointing the loader at your files

Each run creates a **new dated folder** for receipts, but you don't chase the date in
`.env` — set stable paths **once**:

```ini
RECEIPTS_SOURCE_DIR=data          # parent dir, NOT a single dated subfolder
LOYALTY_SOURCE_CSV=data/loyalty_operation_ids.csv
```

The loader scans `RECEIPTS_SOURCE_DIR` recursively (`rglob("*.json")`), so it picks up
**every** dated subfolder from **every** run automatically; the `merge` on `id`
deduplicates overlaps. Likewise the loyalty CSV path is fixed, and the synthetic merge
key accumulates history in DuckDB across runs. So after the first time, step 3 → step 4
needs no `.env` change.

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
product price trends, quantity series. All filterable by year / month / category.

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
uv run python -m carrefour_receipts_api.user_api_extractor   # writes a new data/{YYYYMMDD}/
make build                 # incremental load (recursive glob + merge) + dbt rebuild
make dashboard
```

No `.env` change between runs: with `RECEIPTS_SOURCE_DIR=data` the recursive glob picks
up the new dated folder, and the merge keys deduplicate against what's already in DuckDB.

---

## 8. Full rebuild from scratch

```bash
make clean     # removes carrefour.duckdb and dbt artifacts
# point .env at ALL your archived extracts (or a merged source dir)
make build
```

If you have multiple extract directories (e.g. `data/20240601`, `data/20250101`),
set `RECEIPTS_SOURCE_DIR` to a parent that contains them all — `iter_receipt_files`
scans recursively (`rglob("*.json")`). For loyalty, concatenate your historical CSVs
into one file (with header) and point `LOYALTY_SOURCE_CSV` at it; the merge key
deduplicates overlapping rows automatically.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Extractor returns 403 | Cookies expired | Re-run `make auth-service` → `POST /login` |
| `dbt build` fails on `int_loyalty_matched` | `stg_loyalty` empty (loyalty CSV not loaded) | Check `LOYALTY_SOURCE_CSV` points at a real file, then `make elt` |
| Dashboard shows "marts not found" | `dbt build` not run yet | `make build` |
| Duplicate loyalty rows in DuckDB | Unlikely; if seen after a schema change to `loyalty_row_key` | `make clean && make build` with all archived files |
