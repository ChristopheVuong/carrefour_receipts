-- Order-grain fact for Drive orders, with payment-method breakdown. The Drive
-- equivalent of fct_receipts (same shape so the channel union in int_purchases is clean).
with orders as (
    select * from {{ ref('stg_orders') }}
),

payments as (
    select
        order_number,
        sum(payment_amount) as total_payment,
        sum(case
                when lower(payment_choice) like '%loyalty%'
                  or lower(payment_choice) like '%epay%'
                then payment_amount else 0 end) as loyalty_payment,
        sum(case
                when lower(payment_choice) like 'cb%'
                then payment_amount else 0 end) as card_payment
    from {{ ref('stg_order_payments') }}
    group by 1
)

select
    o.order_number,
    o.order_date,
    o.service_type,
    o.delivery_channel,
    o.order_status,
    o.total_amount                  as total_paid,
    o.total_immediate_discount,
    o.vat_at_20,
    o.vat_at_5,
    coalesce(p.total_payment, 0)    as total_payment,
    coalesce(p.loyalty_payment, 0)  as loyalty_payment,
    coalesce(p.card_payment, 0)     as card_payment
from orders o
left join payments p using (order_number)
