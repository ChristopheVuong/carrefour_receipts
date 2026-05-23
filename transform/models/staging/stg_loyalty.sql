-- Loyalty (fidélité) line items, cleaned and renamed. One row per loyalty line,
-- unnested by dlt from the monthly `history` array into `loyalty__history`.
-- `loyalty_line_id` is a deterministic content key (signature + occurrence) computed
-- here, since a loyalty line has no natural key (`operationId` repeats; `_dlt_id`
-- changes each load). It is the unique grain used by the downstream fidélité fuzzy-join.
with hist as (
    select
        h.operation_id                              as operation_id,
        h.date                                      as loyalty_date,
        h.item_label                                as item_label,
        h.promotion_label                           as promotion_label,
        h.earned                                    as earned_amount,
        h.burned                                    as burned_amount,
        h.item_rd                                   as loyalty_discount,
        h.loyalty_operation                         as loyalty_operation,
        p._id                                       as month_key,
        h._dlt_list_idx                             as line_idx
    from {{ source('raw', 'loyalty__history') }} h
    left join {{ source('raw', 'loyalty') }} p
        on h._dlt_parent_id = p._dlt_id
),

keyed as (
    select
        *,
        concat_ws('|',
            coalesce(operation_id, ''),
            coalesce(cast(loyalty_date as varchar), ''),
            coalesce(trim(item_label), ''),
            coalesce(trim(promotion_label), ''),
            coalesce(cast(round(earned_amount, 4) as varchar), ''),
            coalesce(cast(round(burned_amount, 4) as varchar), ''),
            coalesce(cast(round(loyalty_discount, 4) as varchar), ''),
            coalesce(loyalty_operation, '')
        ) as _signature
    from hist
)

select
    md5(
        _signature || '|'
        || cast(row_number() over (
               partition by _signature order by month_key, line_idx
           ) - 1 as varchar)
    )                                               as loyalty_line_id,
    operation_id,
    cast(loyalty_date as date)                      as loyalty_date,
    item_label,
    promotion_label,
    earned_amount,
    burned_amount,
    loyalty_discount,
    loyalty_operation
from keyed
