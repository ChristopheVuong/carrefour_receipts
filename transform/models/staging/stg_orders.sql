-- Drive order header, cleaned and renamed. One row per order. Flattened from the
-- raw order JSON in the dlt load (the nested productList/offers structure is handled
-- there); here we just rename and cast.
with src as (
    select * from {{ source('raw', 'orders') }}
)

select
    order_number                                  as order_number,
    _dlt_id                                        as order_dlt_key,
    cast(date as date)                             as order_date,
    service_type                                   as service_type,
    delivery_channel                               as delivery_channel,
    order_status                                   as order_status,
    total_amount                                   as total_amount,
    immediate_discount_amount                      as total_immediate_discount,
    vat_at_20                                       as vat_at_20,
    vat_at_5                                        as vat_at_5,
    slot_date_begin                                as slot_begin_at,
    slot_date_end                                  as slot_end_at
from src
