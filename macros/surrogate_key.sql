{#- MD5 over the given columns; NULL is encoded explicitly so (NULL, 'a') and ('a', NULL) differ. -#}
{% macro surrogate_key(columns) -%}
    md5(concat_ws('|'
    {%- for column in columns %},
        coalesce(cast({{ column }} as varchar), '<null>')
    {%- endfor %}
    ))
{%- endmacro %}
