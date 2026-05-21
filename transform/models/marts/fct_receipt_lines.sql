-- Line-item-grain fact: one row per purchased product line, with net price and
-- product categorization. Replaces the legacy `pipeline_prod` (nested
-- $unwind/$group + $getField gymnastics).
--
-- Category: the VAT-based binary heuristic (food/other) is kept as `vat_category`
-- (always populated), and the richer keyword classification from
-- `int_product_categorized` is overlaid as `category` (+ `subcategory`), falling
-- back to `vat_category` when the label scores below the similarity threshold.
with lines as (
    select * from {{ ref('stg_receipt_lines') }}
),

categorized as (
    select * from {{ ref('int_product_categorized') }}
)

select
    l.receipt_id,
    l.receipt_date,
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
