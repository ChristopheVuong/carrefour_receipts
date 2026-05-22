-- Loyalty (fidélité) line items, cleaned and renamed. One row per loyalty line;
-- `loyalty_line_id` is the synthetic merge key (content signature + occurrence,
-- built in the dlt load) — stable across loads, unlike the per-load `_dlt_id`.
-- It is the unique grain used by the downstream fidélité fuzzy-join.
with src as (
    select * from {{ source('raw', 'loyalty') }}
)

select
    loyalty_row_key                                as loyalty_line_id,
    operation_id                                   as operation_id,
    cast(date as date)                             as loyalty_date,
    item_label                                     as item_label,
    promotion_label                                as promotion_label,
    earned                                         as earned_amount,
    burned                                         as burned_amount,
    item_rd                                        as loyalty_discount,
    loyalty_operation                              as loyalty_operation
from src
