-- Loyalty (fidélité) operations, cleaned and renamed. The /loyalty/transactions API
-- returns one entry per operation (a shopping trip's cagnotte movement), not per item:
-- `operationId`, `date`, `store`, `earned` (cagnotte gained), `burned` (cagnotte spent),
-- `canceled`. There is no per-item breakdown at this endpoint. One row per operation.
with src as (
    select * from {{ source('raw', 'loyalty__history') }}
)

select
    operation_id                       as loyalty_operation_id,
    cast(date as date)                 as loyalty_date,
    store                              as store,
    coalesce(earned, 0.0)              as earned_amount,
    coalesce(burned, 0.0)              as burned_amount,
    coalesce(canceled, false)          as is_canceled
from src
