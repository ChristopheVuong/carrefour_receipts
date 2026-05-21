-- Line-item-grain fact: one row per purchased product line, with net price.
-- Replaces the legacy `pipeline_prod` (nested $unwind/$group + $getField gymnastics).
with lines as (
    select * from {{ ref('stg_receipt_lines') }}
)

select
    receipt_id,
    receipt_date,
    line_index,
    product_label,
    category,
    vat_percentage,
    quantity,
    weight,
    unit_price,
    total_price,
    immediate_discount,
    total_price - coalesce(immediate_discount, 0) as total_after_discount
from lines
