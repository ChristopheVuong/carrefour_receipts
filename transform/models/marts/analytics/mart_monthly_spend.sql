-- Monthly spend KPIs per channel: total paid + immediate discount per (month, channel),
-- with rolling 3/6/12-month averages and year-over-year comparison.
--
-- Aggregated to (month, channel) then left-joined onto dim_month_spine × channels so
-- empty months count as 0 and the rolling windows are computed over a gap-free series
-- *within each channel*. Early months have partial windows; YoY is NULL until 13+ months.
-- One row per (year_month, channel). A BI layer sums channels for an all-channel total.
with monthly as (
    select
        strftime(purchase_date, '%Y-%m') as year_month,
        channel,
        sum(total_paid)                  as total_paid,
        sum(total_immediate_discount)    as immediate_discount,
        count(*)                         as purchase_count
    from {{ ref('int_purchases') }}
    group by 1, 2
),

channels as (
    select distinct channel from monthly
),

spine as (
    select
        s.year_month,
        s.month_start,
        s.year,
        s.month,
        c.channel,
        coalesce(m.total_paid, 0)         as total_paid,
        coalesce(m.immediate_discount, 0) as immediate_discount,
        coalesce(m.purchase_count, 0)     as purchase_count
    from {{ ref('dim_month_spine') }} s
    cross join channels c
    left join monthly m
        on m.year_month = s.year_month and m.channel = c.channel
)

select
    year_month,
    year,
    month,
    channel,
    total_paid,
    immediate_discount,
    purchase_count,
    avg(total_paid) over w3                          as total_paid_roll_3m,
    avg(total_paid) over w6                          as total_paid_roll_6m,
    avg(total_paid) over w12                         as total_paid_roll_12m,
    avg(immediate_discount) over w3                  as discount_roll_3m,
    lag(total_paid, 12) over wlag                    as total_paid_prior_year,
    total_paid - lag(total_paid, 12) over wlag       as yoy_abs,
    case
        when lag(total_paid, 12) over wlag > 0
        then (total_paid - lag(total_paid, 12) over wlag)
             / lag(total_paid, 12) over wlag
    end                                              as yoy_pct
from spine
window
    w3   as (partition by channel order by month_start rows between 2  preceding and current row),
    w6   as (partition by channel order by month_start rows between 5  preceding and current row),
    w12  as (partition by channel order by month_start rows between 11 preceding and current row),
    wlag as (partition by channel order by month_start)
order by channel, month_start
