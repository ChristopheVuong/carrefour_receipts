-- Receipt header, cleaned and renamed. Replaces the header part of the
-- legacy MongoDB `pipeline_all` ($unwind/$group pyramid) with plain SQL.
with src as (
    select * from {{ source('raw', 'receipts') }}
)

select
    id                                            as receipt_id,
    _dlt_id                                        as receipt_dlt_key,
    attributes__date_key                           as date_key,
    cast(strptime(attributes__date_key, '%Y%m%d') as date) as receipt_date,
    attributes__gln                                as store_gln,
    attributes__store_name                         as store_name,
    attributes__receipt_number                     as receipt_number,
    attributes__transaction_date                   as transaction_at,
    attributes__loyalty_card_number                as loyalty_card_number,
    attributes__total_amount_before_discount       as total_before_discount,
    attributes__total_amount_immediate_discount    as total_immediate_discount,
    attributes__total_amount_deferred_discount     as total_deferred_discount,
    attributes__total_paid_amount                  as total_paid,
    attributes__total_amount_vats                  as total_vat
from src
