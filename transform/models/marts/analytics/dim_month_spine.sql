-- Contiguous monthly spine from the first to the last receipt month.
--
-- `dim_date` only holds *observed* receipt dates, so months without any shopping
-- are missing. Rolling 3/6/12-month averages and year-over-year (lag 12) windows
-- must run over a gap-free month series, otherwise empty months are silently
-- skipped and the windows span the wrong period. All time-series analytics marts
-- left-join onto this spine.
with bounds as (
    select
        date_trunc('month', min(receipt_date)) as start_month,
        date_trunc('month', max(receipt_date)) as end_month
    from {{ ref('fct_receipts') }}
),

months as (
    select unnest(
        generate_series(start_month, end_month, interval '1 month')
    ) as month_start
    from bounds
)

select
    cast(month_start as date)        as month_start,
    strftime(month_start, '%Y-%m')   as year_month,
    extract(year from month_start)   as year,
    extract(month from month_start)  as month
from months
