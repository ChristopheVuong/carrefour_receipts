-- Purchase-grain union of in-store receipts and Drive orders, tagged with `channel`.
-- Feeds the channel-aware monthly spend mart. Common columns only.
-- `immediate_discount` is normalized to a POSITIVE "amount saved" — receipts store it as
-- a negative reduction, Drive orders as a positive amount, so we flip the receipt sign.
-- `total_before_immediate_discount` = what would have been paid without the immediate
-- (checkout) discount = paid + saved. (NOT the receipt's full gross, which also nets out
-- the deferred cagnotte discount.)
with store as (
    select
        'store'                                              as channel,
        receipt_date                                        as purchase_date,
        coalesce(total_paid, 0)                             as total_paid,
        -coalesce(total_immediate_discount, 0)              as immediate_discount,
        coalesce(total_paid, 0) - coalesce(total_immediate_discount, 0)
                                                            as total_before_immediate_discount
    from {{ ref('fct_receipts') }}
),

drive as (
    select
        'drive'                                             as channel,
        order_date                                          as purchase_date,
        coalesce(total_paid, 0)                             as total_paid,
        coalesce(total_immediate_discount, 0)              as immediate_discount,
        coalesce(total_paid, 0) + coalesce(total_immediate_discount, 0)
                                                            as total_before_immediate_discount
    from {{ ref('fct_orders') }}
)

select * from store
union all
select * from drive
