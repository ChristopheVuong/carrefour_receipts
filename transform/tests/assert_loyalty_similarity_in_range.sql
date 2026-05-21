-- The fidélité match score must be a valid rapidfuzz similarity in [0, 1].
-- A singular test: any returned row is a failure.
select
    loyalty_line_id,
    match_similarity
from {{ ref('int_loyalty_matched') }}
where match_similarity < 0
   or match_similarity > 1
