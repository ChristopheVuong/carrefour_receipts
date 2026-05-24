-- Line-grain union of in-store receipt lines and Drive order lines, tagged with
-- `channel`. Feeds the channel-aware category / price / quantity marts. Common columns
-- only (both facts already overlay the keyword categorization).
with store as (
    select
        'store'              as channel,
        receipt_date         as purchase_date,
        product_label,
        category,
        subcategory,
        vat_percentage,
        quantity,
        weight,
        unit_price,
        total_price,
        immediate_discount,
        total_after_discount
    from {{ ref('fct_receipt_lines') }}
),

drive as (
    select
        'drive'              as channel,
        order_date           as purchase_date,
        product_label,
        category,
        subcategory,
        vat_percentage,
        quantity,
        weight,
        unit_price,
        total_price,
        immediate_discount,
        total_after_discount
    from {{ ref('fct_order_lines') }}
)

select * from store
union all
select * from drive
