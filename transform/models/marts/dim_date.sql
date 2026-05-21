-- Minimal date dimension derived from observed receipt dates.
with dates as (
    select distinct receipt_date as date_day
    from {{ ref('stg_receipts') }}
    where receipt_date is not null
)

select
    date_day,
    extract(year from date_day)        as year,
    extract(month from date_day)       as month,
    extract(day from date_day)         as day,
    strftime(date_day, '%Y-%m')        as year_month
from dates
