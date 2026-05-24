-- Line items joined back to their receipt for date/grain context.
-- Category heuristic mirrors the legacy logic (reduced VAT == food) but also
-- treats the 10% rate (prepared/takeaway food) as food.
with lines as (
    select * from {{ source('raw', 'receipts__attributes__products__product') }}
),

receipts as (
    select * from {{ source('raw', 'receipts') }}
)

select
    r.id                                          as receipt_id,
    cast(strptime(r.attributes__date_key, '%Y%m%d') as date) as receipt_date,
    l._dlt_list_idx                                as line_index,
    l._dlt_id                                      as line_dlt_key,
    l.label                                        as product_label,
    l.vat_percentage                               as vat_percentage,
    l.quantity                                     as quantity,
    l.weight                                       as weight,
    l.unit_type_code                               as unit_type_code,
    l.unit_price                                   as unit_price,
    l.total_price                                  as total_price,
    l.immediate_discount                           as immediate_discount,
    case
        when l.vat_percentage in ('5.5', '10.0') then 'food'
        else 'other'
    end                                            as category
from lines l
inner join receipts r
    on l._dlt_parent_id = r._dlt_id
