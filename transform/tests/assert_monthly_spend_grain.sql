-- mart_monthly_spend must have one row per (year_month, channel).
-- A singular test: any returned row (a duplicated grain) is a failure.
select
    year_month,
    channel,
    count(*) as n
from {{ ref('mart_monthly_spend') }}
group by 1, 2
having count(*) > 1
