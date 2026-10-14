-- Zone dimension: one row per TLC taxi zone, labels filled so BI tools never group by NULL.
select
    location_id as zone_key,
    coalesce(borough, 'Unknown') as borough,
    coalesce(zone_name, 'Unknown') as zone_name,
    coalesce(service_zone, 'Unknown') as service_zone,
    coalesce(service_zone in ('Airports', 'EWR'), false) as is_airport
from {{ ref('stg_tlc__taxi_zones') }}
