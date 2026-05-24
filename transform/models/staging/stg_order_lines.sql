-- Drive order line items joined back to their order for date/grain context. Columns
-- mirror `stg_receipt_lines` so the categorization and channel-union models can treat
-- store and Drive lines uniformly. Orders carry no per-line VAT, so `vat_percentage`
-- is null and the VAT-based `category` fallback is always 'other' — the keyword
-- categorization (int_product_categorized) supplies the real category in fct_order_lines.
with lines as (
    select * from {{ source('raw', 'orders__lines') }}
),

orders as (
    select * from {{ source('raw', 'orders') }}
)

select
    o.order_number                                 as order_number,
    cast(o.date as date)                           as order_date,
    l.order_line_index                             as line_index,
    o.order_number || '-' || l.order_line_index    as order_line_id,
    l.title                                         as product_label,
    l.brand                                         as brand,
    l.ean                                           as ean,
    l.order_category_code                           as order_category_code,
    cast(null as varchar)                          as vat_percentage,
    l.qty_requested                                as quantity,
    cast(null as double)                           as weight,
    l.unit_price                                   as unit_price,
    l.line_total                                   as total_price,
    l.immediate_discount                           as immediate_discount,
    'other'                                        as category
from lines l
inner join orders o
    on l._dlt_parent_id = o._dlt_id
