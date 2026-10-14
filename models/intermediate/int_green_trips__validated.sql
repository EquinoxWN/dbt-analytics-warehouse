-- Every staged record with exactly one outcome: kept (rejection_reason is NULL) or rejected for the
-- first rule it breaks. Nothing is dropped here, so source rows = kept + rejected always holds.
with trips as (

    select * from {{ ref('stg_tlc__green_trips') }}

),

zones as (

    select location_id from {{ ref('stg_tlc__taxi_zones') }}

),

numbered as (

    select
        trips.*,
        row_number() over (
            partition by trips.trip_id
            order by trips.source_file, trips.pickup_at
        ) as copy_number,
        pickup_zone.location_id is not null as has_known_pickup_zone,
        dropoff_zone.location_id is not null as has_known_dropoff_zone
    from trips
    left join zones as pickup_zone
        on trips.pickup_location_id = pickup_zone.location_id
    left join zones as dropoff_zone
        on trips.dropoff_location_id = dropoff_zone.location_id

),

classified as (

    select
        *,
        case
            when copy_number > 1
                then 'duplicate_record'
            when pickup_at is null or dropoff_at is null
                then 'missing_timestamp'
            when dropoff_at <= pickup_at
                then 'dropoff_not_after_pickup'
            when dropoff_at - pickup_at > to_hours({{ var('max_trip_duration_hours') }})
                then 'duration_over_limit'
            when date_trunc('month', pickup_at) <> source_month
                then 'pickup_outside_file_month'
            when total_amount < 0 or fare_amount < 0
                then 'negative_amount'
            when trip_distance_miles < 0 or trip_distance_miles > {{ var('max_trip_distance_miles') }}
                then 'distance_out_of_range'
            when not has_known_pickup_zone or not has_known_dropoff_zone
                then 'unknown_zone'
        end as rejection_reason
    from numbered

)

select
    * exclude (copy_number, has_known_pickup_zone, has_known_dropoff_zone),
    rejection_reason is null as is_valid
from classified
