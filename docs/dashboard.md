# Dashboard

An interactive [Streamlit](https://streamlit.io/) app over the dbt analytics marts:
headline KPIs, monthly spend with a rolling average, category breakdown, product
price trends and quantity series — all filterable by year / month / category /
**channel** (All / store / Drive; "All" sums the two).

Source: [dashboard/app.py](../src/carrefour_receipts_api/dashboard/app.py). It reads the
marts (`mart_monthly_spend`, `mart_category_insights`, `mart_product_prices`,
`mart_quantities`) from the DuckDB file at `config.DUCKDB_PATH`.

## Prerequisite

Build the marts first — the dashboard only reads them:

```bash
make build      # dlt load + dbt build  -> ./carrefour.duckdb
```

If the marts are missing the app shows a hint instead of charts.

## Run locally

```bash
uv sync --extra dashboard
make dashboard
# = streamlit run src/carrefour_receipts_api/dashboard/app.py  -> http://localhost:8501
```

## Run with Docker

The image ships only the dashboard surface and expects a host-built DuckDB file mounted
read-only at `/data/carrefour.duckdb`.

```bash
make docker-build                       # docker build -t carrefour-dashboard .
make docker-run                         # mounts ./carrefour.duckdb, serves :8501
# or, equivalently:
docker compose up --build               # uses docker-compose.yml
```

Open <http://localhost:8501>. To point at a different database, set `DUCKDB_PATH` (the
compose file already maps it to the mounted volume).
