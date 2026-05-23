-- Line-item-grain fact for Drive orders, with net price and product categorization.
-- The Drive equivalent of fct_receipt_lines (same output columns so the channel union
-- in int_purchase_lines is clean). Orders have no per-line VAT, so `vat_category` is the
-- 'other' fallback and `category` comes from the keyword classification overlay.
with lines as (
    select * from {{ ref('stg_order_lines') }}
),

categorized as (
    select * from {{ ref('int_product_categorized') }}
)

select
    l.order_number,
    l.order_line_id,
    l.order_date,
    l.line_index,
    l.product_label,
    l.category                                    as vat_category,
    coalesce(c.category, l.category)              as category,
    c.subcategory                                 as subcategory,
    coalesce(c.match_confidence, 0.0)             as category_confidence,
    l.vat_percentage,
    l.quantity,
    l.weight,
    l.unit_price,
    l.total_price,
    l.immediate_discount,
    l.total_price - coalesce(l.immediate_discount, 0) as total_after_discount
from lines l
left join categorized c
    on l.product_label = c.product_label
