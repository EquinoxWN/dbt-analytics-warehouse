-- Valid trips joined to zones and code lists, with derived measures ready for the fact table.
with trips as (

    select * from {{ ref('int_green_trips__validated') }}
    where is_valid

),

zones as (

    select * from {{ ref('stg_tlc__taxi_zones') }}

),

vendors as (select * from {{ ref('tlc_vendors') }}),
rate_codes as (select * from {{ ref('tlc_rate_codes') }}),
payment_types as (select * from {{ ref('tlc_payment_types') }}),
trip_types as (select * from {{ ref('tlc_trip_types') }}),

enriched as (

    select
        trips.trip_id,
        trips.pickup_at,
        trips.dropoff_at,
        cast(trips.pickup_at as date) as pickup_date,
        hour(trips.pickup_at) as pickup_hour,
        trips.pickup_location_id,
        pickup_zone.borough as pickup_borough,
        pickup_zone.zone_name as pickup_zone_name,
        trips.dropoff_location_id,
        dropoff_zone.borough as dropoff_borough,
        dropoff_zone.zone_name as dropoff_zone_name,

        trips.vendor_id,
        coalesce(vendors.vendor_name, 'Unknown') as vendor_name,
        trips.rate_code_id,
        coalesce(rate_codes.rate_code_name, 'Unknown') as rate_code_name,
        trips.payment_type_id,
        coalesce(payment_types.payment_type_name, 'Unknown') as payment_type_name,
        trips.trip_type_id,
        coalesce(trip_types.trip_type_name, 'Unknown') as trip_type_name,
        trips.is_store_and_forward,

        trips.passenger_count,
        trips.trip_distance_miles,
        cast(
            round(date_diff('second', trips.pickup_at, trips.dropoff_at) / 60.0, 2)
            as decimal(10, 2)
        ) as trip_duration_minutes,
        cast(
            round(
                trips.trip_distance_miles
                / (date_diff('second', trips.pickup_at, trips.dropoff_at) / 3600.0),
                2
            ) as decimal(10, 2)
        ) as average_speed_mph,
        trips.fare_amount,
        trips.extra_amount,
        trips.mta_tax_amount,
        trips.tip_amount,
        trips.tolls_amount,
        trips.improvement_surcharge_amount,
        trips.congestion_surcharge_amount,
        trips.total_amount,
        (
            trips.rate_code_id in (2, 3)
            or pickup_zone.service_zone in ('Airports', 'EWR')
            or dropoff_zone.service_zone in ('Airports', 'EWR')
        ) is true as is_airport_trip,
        trips.source_file

    from trips
    inner join zones as pickup_zone
        on trips.pickup_location_id = pickup_zone.location_id
    inner join zones as dropoff_zone
        on trips.dropoff_location_id = dropoff_zone.location_id
    left join vendors on trips.vendor_id = vendors.vendor_id
    left join rate_codes on trips.rate_code_id = rate_codes.rate_code_id
    left join payment_types on trips.payment_type_id = payment_types.payment_type_id
    left join trip_types on trips.trip_type_id = trip_types.trip_type_id

)

select * from enriched
