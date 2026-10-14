-- One row per taxi zone: cast the id, trim text, turn the file's 'N/A' placeholders into NULL.
with source as (

    select * from {{ source('tlc', 'taxi_zone_lookup') }}

),

renamed as (

    select
        cast(trim(LocationID) as integer) as location_id,
        nullif(nullif(trim(Borough), 'N/A'), 'Unknown') as borough,
        nullif(trim(Zone), 'N/A') as zone_name,
        nullif(trim(service_zone), 'N/A') as service_zone
    from source

)

select * from renamed
