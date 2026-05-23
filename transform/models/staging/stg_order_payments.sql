-- Payment splits per Drive order (card, loyalty wallet, PayPal...). Mirrors
-- `stg_payments`; `payment_choice` values are e.g. CB, CBPASS, eLOYALTY, CARREFOUR_EPAY.
with payments as (
    select * from {{ source('raw', 'orders__payments') }}
),

orders as (
    select * from {{ source('raw', 'orders') }}
)

select
    o.order_number    as order_number,
    p.choice          as payment_choice,
    p.amount          as payment_amount
from payments p
inner join orders o
    on p._dlt_parent_id = o._dlt_id
