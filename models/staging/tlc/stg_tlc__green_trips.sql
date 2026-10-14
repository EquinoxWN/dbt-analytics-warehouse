-- One row per raw record: rename to snake_case, cast to exact types, clean codes. No rows dropped.
with source as (

    select * from {{ source('tlc', 'green_tripdata') }}

),

renamed as (

    select
        {{ surrogate_key([
            'VendorID', 'lpep_pickup_datetime', 'lpep_dropoff_datetime', 'store_and_fwd_flag',
            'RatecodeID', 'PULocationID', 'DOLocationID', 'passenger_count', 'trip_distance',
            'fare_amount', 'extra', 'mta_tax', 'tip_amount', 'tolls_amount',
            'improvement_surcharge', 'total_amount', 'payment_type', 'trip_type',
            'congestion_surcharge'
        ]) }} as trip_id,

        cast(VendorID as integer) as vendor_id,
        cast(lpep_pickup_datetime as timestamp) as pickup_at,
        cast(lpep_dropoff_datetime as timestamp) as dropoff_at,
        case upper(trim(store_and_fwd_flag))
            when 'Y' then true
            when 'N' then false
        end as is_store_and_forward,
        -- Code 99 means "Null/unknown" in the data dictionary.
        cast(nullif(RatecodeID, 99) as integer) as rate_code_id,
        cast(PULocationID as integer) as pickup_location_id,
        cast(DOLocationID as integer) as dropoff_location_id,
        cast(passenger_count as integer) as passenger_count,
        cast(round(trip_distance, 2) as decimal(12, 2)) as trip_distance_miles,
        {{ to_money('fare_amount') }} as fare_amount,
        {{ to_money('extra') }} as extra_amount,
        {{ to_money('mta_tax') }} as mta_tax_amount,
        {{ to_money('tip_amount') }} as tip_amount,
        {{ to_money('tolls_amount') }} as tolls_amount,
        {{ to_money('improvement_surcharge') }} as improvement_surcharge_amount,
        {{ to_money('congestion_surcharge') }} as congestion_surcharge_amount,
        {{ to_money('total_amount') }} as total_amount,
        cast(payment_type as integer) as payment_type_id,
        cast(trip_type as integer) as trip_type_id,
        -- ehail_fee is empty in every file since 2019 and is not carried forward.

        regexp_extract(replace(filename, '\', '/'), '[^/]+$') as source_file,
        cast(
            strptime(regexp_extract(filename, '(\d{4}-\d{2})\.parquet$', 1) || '-01', '%Y-%m-%d')
            as date
        ) as source_month

    from source

)

select * from renamed
