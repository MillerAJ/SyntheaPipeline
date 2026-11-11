{#
  Strip the "urn:uuid:" prefix from a FHIR reference so it joins to the target resource's id.
  References that are not urn:uuid (e.g. "Practitioner?identifier=...") are returned unchanged.
#}
{% macro fhir_id(expr) -%}
    nullif(regexp_replace({{ expr }}, '^urn:uuid:', ''), '')
{%- endmacro %}
