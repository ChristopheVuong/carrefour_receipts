-- Payment splits per receipt (card, loyalty wallet, vouchers...).
with payments as (
    select * from {{ source('raw', 'receipts__attributes__payment_info') }}
),

receipts as (
    select * from {{ source('raw', 'receipts') }}
)

select
    r.id          as receipt_id,
    p.choice      as payment_choice,
    p.type        as payment_type_code,
    p.amount      as payment_amount
from payments p
inner join receipts r
    on p._dlt_parent_id = r._dlt_id
