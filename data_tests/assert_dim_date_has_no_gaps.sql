-- Fails when dim_date skips or repeats a day between its first and last date.
select count(*) as days, min(date_day) as first_day, max(date_day) as last_day
from {{ ref('dim_date') }}
having count(*) <> date_diff('day', min(date_day), max(date_day)) + 1
