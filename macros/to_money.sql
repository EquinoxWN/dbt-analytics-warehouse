{#- Cast a TLC dollar amount (DOUBLE in the parquet files) to an exact two-decimal value. -#}
{% macro to_money(column) -%}
    cast(round({{ column }}, 2) as decimal(12, 2))
{%- endmacro %}
