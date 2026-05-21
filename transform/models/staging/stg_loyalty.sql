-- Loyalty (fidélité) line items, cleaned and renamed. One row per loyalty line;
-- `loyalty_line_id` (dlt surrogate key) is the stable unique grain used by the
-- downstream fidélité fuzzy-join.
with src as (
    select * from {{ source('raw', 'loyalty') }}
)

select
    _dlt_id                                        as loyalty_line_id,
    operation_id                                   as operation_id,
    cast(date as date)                             as loyalty_date,
    item_label                                     as item_label,
    promotion_label                                as promotion_label,
    earned                                         as earned_amount,
    burned                                         as burned_amount,
    item_rd                                        as loyalty_discount,
    loyalty_operation                              as loyalty_operation
from src
