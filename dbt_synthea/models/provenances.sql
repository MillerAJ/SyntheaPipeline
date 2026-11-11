{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS provenance_id,
    {{ fhir_id("resource -> 'target' -> 0 ->> 'reference'") }}               AS patient_id,
    (resource ->> 'recorded')::timestamptz                                   AS recorded_at,
    jsonb_array_length(resource -> 'target')                                 AS target_count,
    resource -> 'agent' -> 0 -> 'who' ->> 'display'                          AS agent_name,
    resource -> 'agent' -> 0 -> 'onBehalfOf' ->> 'display'                   AS agent_organization_name
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Provenance'
