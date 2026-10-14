-- Where every raw record went, per source file: 'loaded' into fact_trips or the rejection reason.
select
    source_file,
    coalesce(rejection_reason, 'loaded') as outcome,
    count(*) as trip_count,
    cast(sum(total_amount) as decimal(18, 2)) as total_amount
from {{ ref('int_green_trips__validated') }}
group by all
