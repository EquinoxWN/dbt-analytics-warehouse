-- Fails for any source file where staged records <> rows in fact_trips + rejected records.
with staged as (
    select source_file, count(*) as staged_rows
    from {{ ref('stg_tlc__green_trips') }}
    group by all
),

loaded as (
    select source_file, count(*) as loaded_rows
    from {{ ref('fact_trips') }}
    group by all
),

rejected as (
    select source_file, count(*) as rejected_rows
    from {{ ref('int_green_trips__validated') }}
    where not is_valid
    group by all
)

select
    staged.source_file,
    staged.staged_rows,
    coalesce(loaded.loaded_rows, 0) as loaded_rows,
    coalesce(rejected.rejected_rows, 0) as rejected_rows
from staged
left join loaded using (source_file)
left join rejected using (source_file)
where staged.staged_rows <> coalesce(loaded.loaded_rows, 0) + coalesce(rejected.rejected_rows, 0)
