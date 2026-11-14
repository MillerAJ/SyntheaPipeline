{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS observation_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'encounter' ->> 'reference'") }}                 AS encounter_id,
    resource ->> 'status'                                                    AS status,
    resource -> 'category' -> 0 -> 'coding' -> 0 ->> 'code'                  AS category_code,
    resource -> 'code' -> 'coding' -> 0 ->> 'code'                           AS code,
    resource -> 'code' -> 'coding' -> 0 ->> 'display'                        AS description,
    (resource ->> 'effectiveDateTime')::timestamptz                          AS effective_at,
    (resource ->> 'issued')::timestamptz                                     AS issued_at,
    (resource -> 'valueQuantity' ->> 'value')::numeric                       AS value_quantity,
    resource -> 'valueQuantity' ->> 'unit'                                   AS value_unit,
    resource ->> 'valueString'                                               AS value_string,
    resource -> 'valueCodeableConcept' -> 'coding' -> 0 ->> 'code'           AS value_code,
    resource -> 'valueCodeableConcept' -> 'coding' -> 0 ->> 'display'        AS value_display,
    jsonb_array_length(resource -> 'component')                              AS component_count,
    resource -> 'category' -> 0 -> 'coding' -> 0 ->> 'display'                                       AS category_display,
    resource -> 'code' ->> 'text'                                                                    AS code_text,
    resource -> 'valueQuantity' ->> 'code'                                                           AS value_unit_code,
    resource -> 'valueCodeableConcept' ->> 'text'                                                    AS value_text
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Observation'
