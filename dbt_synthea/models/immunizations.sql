{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS immunization_id,
    {{ fhir_id("resource -> 'patient' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'encounter' ->> 'reference'") }}                 AS encounter_id,
    resource ->> 'status'                                                    AS status,
    resource -> 'vaccineCode' -> 'coding' -> 0 ->> 'code'                    AS code,
    resource -> 'vaccineCode' -> 'coding' -> 0 ->> 'display'                 AS description,
    (resource ->> 'occurrenceDateTime')::timestamptz                         AS occurrence_at,
    (resource ->> 'primarySource')::boolean                                  AS primary_source,
    resource -> 'location' ->> 'display'                                     AS location_name
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Immunization'
