-- Fails when the enrichment joins add, lose or change money: fact totals must equal valid records.
with valid as (
    select count(*) as trips, sum(total_amount) as total_amount, sum(tip_amount) as tip_amount
    from {{ ref('int_green_trips__validated') }}
    where is_valid
),

fact as (
    select count(*) as trips, sum(total_amount) as total_amount, sum(tip_amount) as tip_amount
    from {{ ref('fact_trips') }}
)

select valid.*, fact.trips as fact_trips, fact.total_amount as fact_total_amount
from valid, fact
where valid.trips <> fact.trips
    or valid.total_amount is distinct from fact.total_amount
    or valid.tip_amount is distinct from fact.tip_amount
