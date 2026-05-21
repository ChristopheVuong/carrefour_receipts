-- Per-product monthly unit-price series, for tracking price evolution of the most
-- frequently bought products and configurable baskets (vegetables, meat).
--
-- Grain: one row per (product_label, year_month). `is_top_product` flags products
-- bought often enough to chart a trend; `in_basket` flags the staple food baskets.
with monthly_price as (
    select
        product_label,
        subcategory,
        strftime(receipt_date, '%Y-%m')           as year_month,
        sum(total_price) / nullif(sum(quantity), 0) as avg_unit_price,
        sum(quantity)                              as quantity,
        count(*)                                   as line_count
    from {{ ref('fct_receipt_lines') }}
    group by 1, 2, 3
),

product_totals as (
    select product_label, sum(quantity) as total_quantity
    from monthly_price
    group by 1
)

select
    mp.product_label,
    mp.subcategory,
    mp.year_month,
    mp.avg_unit_price,
    mp.quantity,
    mp.line_count,
    pt.total_quantity,
    (pt.total_quantity >= 5)                          as is_top_product,
    (mp.subcategory in ('vegetable', 'fruit', 'meat')) as in_basket
from monthly_price mp
join product_totals pt using (product_label)
order by mp.product_label, mp.year_month
