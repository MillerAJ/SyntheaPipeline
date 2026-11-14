{{ config(materialized='table', schema='flat') }}

{# One row per resource this provenance covers; large but cheap (a single id column). #}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS provenance_id,
    {{ fhir_id("b.resource -> 'target' -> 0 ->> 'reference'") }}                                     AS patient_id,
    {{ fhir_id("t.tgt ->> 'reference'") }}                                                           AS target_id
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'target') AS t(tgt)
WHERE b.resource_type = 'Provenance'
