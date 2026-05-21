-- Monthly quantity KPIs: kilograms of fruit/veg, total items, and rolling
-- consumption of hygiene/household-detergent items. Built over dim_month_spine so
-- empty months are 0 and the rolling windows are correct.
--
-- Note: detergent *volume* (liters) is not derivable yet — the unit/volume isn't
-- parsed from labels — so this tracks item counts; liters is a future enhancement.
with monthly as (
    select
        strftime(receipt_date, '%Y-%m') as year_month,
        sum(case when subcategory in ('fruit', 'vegetable') then coalesce(weight, 0) else 0 end) as fruit_veg_kg,
        sum(quantity)                                                                            as total_items,
        sum(case when category = 'hygiene_beauty' then quantity else 0 end)                      as hygiene_items,
        sum(case when subcategory in ('laundry', 'dishwashing', 'cleaning') then quantity else 0 end) as detergent_items
    from {{ ref('fct_receipt_lines') }}
    group by 1
),

spine as (
    select
        s.year_month,
        s.month_start,
        coalesce(m.fruit_veg_kg, 0)    as fruit_veg_kg,
        coalesce(m.total_items, 0)     as total_items,
        coalesce(m.hygiene_items, 0)   as hygiene_items,
        coalesce(m.detergent_items, 0) as detergent_items
    from {{ ref('dim_month_spine') }} s
    left join monthly m using (year_month)
)

select
    year_month,
    fruit_veg_kg,
    total_items,
    hygiene_items,
    detergent_items,
    avg(total_items) over w3      as items_roll_3m,
    sum(hygiene_items) over w6    as hygiene_roll_6m,
    sum(detergent_items) over w12 as detergent_roll_12m
from spine
window
    w3  as (order by month_start rows between 2  preceding and current row),
    w6  as (order by month_start rows between 5  preceding and current row),
    w12 as (order by month_start rows between 11 preceding and current row)
order by month_start
