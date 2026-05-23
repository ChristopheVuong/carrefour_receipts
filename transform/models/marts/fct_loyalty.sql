-- Operation-grain fidélité fact: one row per loyalty operation, with the cagnotte
-- earned and burned. Replaces the old line-grain fct_loyalty_lines (the API exposes
-- loyalty only at operation level, so there is no item match to a receipt line).
select
    loyalty_operation_id,
    loyalty_date,
    store,
    earned_amount,
    burned_amount,
    is_canceled
from {{ ref('stg_loyalty') }}
