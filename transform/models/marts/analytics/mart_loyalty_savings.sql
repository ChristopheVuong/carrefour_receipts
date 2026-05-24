-- Monthly fidélité savings (store programme): cagnotte earned vs. burned per month.
-- Store fidélité only (the programme is in-store; Drive carries no fidélité), so there
-- is no `channel` here. One row per year_month. Canceled operations are excluded.
--
-- `loyalty_savings` = cagnotte earned this month (what the programme gave back);
-- `burned_amount` (cagnotte spent) is reported separately, not netted.
with ops as (
    select
        strftime(loyalty_date, '%Y-%m') as year_month,
        earned_amount,
        burned_amount
    from {{ ref('fct_loyalty') }}
    where not is_canceled
)

select
    year_month,
    sum(earned_amount) as earned_amount,
    sum(burned_amount) as burned_amount,
    sum(earned_amount) as loyalty_savings,
    count(*)           as operation_count
from ops
group by 1
order by 1
