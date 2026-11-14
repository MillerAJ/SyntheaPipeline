{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS observation_id,
    {{ fhir_id("b.resource -> 'subject' ->> 'reference'") }}                                         AS patient_id,
    {{ fhir_id("b.resource -> 'encounter' ->> 'reference'") }}                                       AS encounter_id,
    c.seq::int                                                                                       AS component_seq,
    c.comp -> 'code' -> 'coding' -> 0 ->> 'code'                                                     AS code,
    c.comp -> 'code' -> 'coding' -> 0 ->> 'display'                                                  AS description,
    (c.comp -> 'valueQuantity' ->> 'value')::numeric                                                 AS value_quantity,
    c.comp -> 'valueQuantity' ->> 'unit'                                                             AS value_unit,
    c.comp -> 'valueQuantity' ->> 'code'                                                             AS value_unit_code,
    c.comp -> 'valueCodeableConcept' -> 'coding' -> 0 ->> 'code'                                     AS value_code,
    c.comp -> 'valueCodeableConcept' -> 'coding' -> 0 ->> 'display'                                  AS value_display,
    c.comp ->> 'valueString'                                                                         AS value_string
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'component') WITH ORDINALITY AS c(comp, seq)
WHERE b.resource_type = 'Observation'
