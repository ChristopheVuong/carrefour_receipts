-- Monthly spend KPIs: total paid + immediate discount per month, with rolling
-- 3/6/12-month averages and year-over-year comparison.
--
-- Aggregated to month then left-joined onto dim_month_spine so empty months count
-- as 0 and the rolling windows are computed over a gap-free series. Early months
-- have partial windows (fewer than N preceding rows) — that is expected; YoY is
-- NULL until there are 13+ months of history.
with monthly as (
    select
        strftime(receipt_date, '%Y-%m') as year_month,
        sum(total_paid)                 as total_paid,
        sum(total_immediate_discount)   as immediate_discount,
        count(*)                        as receipt_count
    from {{ ref('fct_receipts') }}
    group by 1
),

spine as (
    select
        s.year_month,
        s.month_start,
        s.year,
        s.month,
        coalesce(m.total_paid, 0)         as total_paid,
        coalesce(m.immediate_discount, 0) as immediate_discount,
        coalesce(m.receipt_count, 0)      as receipt_count
    from {{ ref('dim_month_spine') }} s
    left join monthly m using (year_month)
)

select
    year_month,
    year,
    month,
    total_paid,
    immediate_discount,
    receipt_count,
    avg(total_paid) over w3                          as total_paid_roll_3m,
    avg(total_paid) over w6                          as total_paid_roll_6m,
    avg(total_paid) over w12                         as total_paid_roll_12m,
    avg(immediate_discount) over w3                  as discount_roll_3m,
    lag(total_paid, 12) over (order by month_start)  as total_paid_prior_year,
    total_paid - lag(total_paid, 12) over (order by month_start) as yoy_abs,
    case
        when lag(total_paid, 12) over (order by month_start) > 0
        then (total_paid - lag(total_paid, 12) over (order by month_start))
             / lag(total_paid, 12) over (order by month_start)
    end                                              as yoy_pct
from spine
window
    w3  as (order by month_start rows between 2  preceding and current row),
    w6  as (order by month_start rows between 5  preceding and current row),
    w12 as (order by month_start rows between 11 preceding and current row)
order by month_start
