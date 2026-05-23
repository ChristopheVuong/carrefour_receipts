-- Purchase-grain union of in-store receipts and Drive orders, tagged with `channel`.
-- Feeds the channel-aware monthly spend mart. Common columns only.
with store as (
    select
        'store'                  as channel,
        receipt_date             as purchase_date,
        total_paid               as total_paid,
        total_immediate_discount as total_immediate_discount
    from {{ ref('fct_receipts') }}
),

drive as (
    select
        'drive'                  as channel,
        order_date               as purchase_date,
        total_paid               as total_paid,
        total_immediate_discount as total_immediate_discount
    from {{ ref('fct_orders') }}
)

select * from store
union all
select * from drive
