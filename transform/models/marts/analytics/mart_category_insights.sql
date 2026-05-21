-- Category spend per month: total, bio share, non-food (VAT 20%) share, and a
-- meat-vs-plant proxy from the product subcategory. Long format — one row per
-- (year_month, category) — so a BI layer can compute shares against a monthly total.
with lines as (
    select
        strftime(receipt_date, '%Y-%m')                  as year_month,
        category,
        subcategory,
        vat_percentage,
        total_after_discount,
        lower(product_label) like '%bio%'                as is_bio,
        case
            when subcategory in ('meat', 'fish')         then 'meat'
            when subcategory in ('vegetable', 'fruit')   then 'plant'
        end                                              as diet_proxy
    from {{ ref('fct_receipt_lines') }}
)

select
    year_month,
    category,
    count(*)                                                                as line_count,
    sum(total_after_discount)                                               as spend,
    sum(case when is_bio then total_after_discount else 0 end)              as bio_spend,
    sum(case when vat_percentage = '20.0' then total_after_discount else 0 end) as non_food_vat_spend,
    sum(case when diet_proxy = 'meat'  then total_after_discount else 0 end)    as meat_spend,
    sum(case when diet_proxy = 'plant' then total_after_discount else 0 end)    as plant_spend
from lines
group by 1, 2
order by 1, 2
