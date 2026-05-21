-- mart_category_insights must have one row per (year_month, category).
-- A singular test: any returned row (a duplicated grain) is a failure.
select
    year_month,
    category,
    count(*) as n
from {{ ref('mart_category_insights') }}
group by 1, 2
having count(*) > 1
