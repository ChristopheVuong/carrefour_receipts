-- mart_product_prices must have one row per (product_label, year_month, channel).
-- A singular test: any returned row (a duplicated grain) is a failure.
select
    product_label,
    year_month,
    channel,
    count(*) as n
from {{ ref('mart_product_prices') }}
group by 1, 2, 3
having count(*) > 1
