-- Receipt-grain fact with payment-method breakdown. This is the SQL equivalent
-- of the legacy `pipeline_all` + pandas pivot in `main_amounts`, but testable.
with receipts as (
    select * from {{ ref('stg_receipts') }}
),

payments as (
    select
        receipt_id,
        sum(payment_amount) as total_payment,
        sum(case
                when lower(payment_choice) like '%fidelite%'
                  or lower(payment_choice) like '%cagnotte%'
                  or lower(payment_choice) like '%eloyalty%'
                then payment_amount else 0 end) as loyalty_payment,
        sum(case
                when lower(payment_choice) like '%carte bancaire%'
                then payment_amount else 0 end) as card_payment
    from {{ ref('stg_payments') }}
    group by 1
)

select
    r.receipt_id,
    r.receipt_date,
    r.store_name,
    r.total_before_discount,
    r.total_immediate_discount,
    r.total_deferred_discount,
    r.total_paid,
    r.total_vat,
    coalesce(p.total_payment, 0)   as total_payment,
    coalesce(p.loyalty_payment, 0) as loyalty_payment,
    coalesce(p.card_payment, 0)    as card_payment
from receipts r
left join payments p using (receipt_id)
