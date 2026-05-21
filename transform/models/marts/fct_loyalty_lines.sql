-- Loyalty-line-grain fact: one row per fidélité line item, with its fuzzy-matched
-- receipt product label. This is the modern-stack equivalent of the legacy
-- loyalty<->product join (`pandas_postprocessing.main_matching` / `main_merging`).
with matched as (
    select * from {{ ref('int_loyalty_matched') }}
)

select
    loyalty_line_id,
    operation_id,
    loyalty_date,
    item_label,
    loyalty_operation,
    earned_amount,
    burned_amount,
    loyalty_discount,
    matched_line_id,
    matched_label,
    match_similarity,
    matched_label is not null as is_matched
from matched
