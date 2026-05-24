-- The month spine must be gap-free: consecutive rows are exactly one month apart.
-- A singular test: any returned row (a gap larger than one month) is a failure.
with ordered as (
    select
        month_start,
        lag(month_start) over (order by month_start) as prev_month
    from {{ ref('dim_month_spine') }}
)

select
    month_start,
    prev_month
from ordered
where prev_month is not null
  and month_start <> prev_month + interval '1 month'
