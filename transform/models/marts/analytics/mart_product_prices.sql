-- Per-product monthly unit-price series per channel, for tracking price evolution of
-- the most frequently bought products and configurable baskets (vegetables, meat).
--
-- Grain: one row per (product_label, year_month, channel). `is_top_product` flags
-- products bought often enough (across channels) to chart a trend; `in_basket` flags
-- the staple food baskets.
with monthly_price as (
    select
        product_label,
        subcategory,
        channel,
        strftime(purchase_date, '%Y-%m')           as year_month,
        sum(total_price) / nullif(sum(quantity), 0) as avg_unit_price,
        sum(quantity)                              as quantity,
        count(*)                                   as line_count
    from {{ ref('int_purchase_lines') }}
    group by 1, 2, 3, 4
),

product_totals as (
    select product_label, sum(quantity) as total_quantity
    from monthly_price
    group by 1
)

select
    mp.product_label,
    mp.subcategory,
    mp.channel,
    mp.year_month,
    mp.avg_unit_price,
    mp.quantity,
    mp.line_count,
    pt.total_quantity,
    (pt.total_quantity >= 5)                          as is_top_product,
    (mp.subcategory in ('vegetable', 'fruit', 'meat')) as in_basket
from monthly_price mp
join product_totals pt using (product_label)
order by mp.product_label, mp.channel, mp.year_month
