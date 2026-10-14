-- Date dimension: every day of each calendar year that has at least one loaded trip.
with bounds as (

    select
        date_trunc('year', min(pickup_date)) as first_day,
        date_trunc('year', max(pickup_date)) + interval 1 year - interval 1 day as last_day
    from {{ ref('int_green_trips__enriched') }}

),

days as (

    select cast(unnest(generate_series(first_day, last_day, interval 1 day)) as date) as date_day
    from bounds
    where first_day is not null

)

select
    cast(strftime(date_day, '%Y%m%d') as integer) as date_key,
    date_day,
    cast(year(date_day) as integer) as year_number,
    cast(quarter(date_day) as integer) as quarter_number,
    cast(month(date_day) as integer) as month_number,
    strftime(date_day, '%B') as month_name,
    cast(day(date_day) as integer) as day_of_month,
    cast(dayofyear(date_day) as integer) as day_of_year,
    cast(isodow(date_day) as integer) as iso_day_of_week,
    strftime(date_day, '%A') as day_name,
    isodow(date_day) in (6, 7) as is_weekend,
    cast(weekofyear(date_day) as integer) as iso_week_number
from days
