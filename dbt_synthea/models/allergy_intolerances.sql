{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS allergy_intolerance_id,
    {{ fhir_id("resource -> 'patient' ->> 'reference'") }}                   AS patient_id,
    resource ->> 'type'                                                      AS allergy_type,
    resource -> 'category' ->> 0                                             AS category,
    resource ->> 'criticality'                                               AS criticality,
    resource -> 'code' -> 'coding' -> 0 ->> 'code'                           AS code,
    resource -> 'code' -> 'coding' -> 0 ->> 'display'                        AS description,
    resource -> 'clinicalStatus' -> 'coding' -> 0 ->> 'code'                 AS clinical_status,
    resource -> 'verificationStatus' -> 'coding' -> 0 ->> 'code'             AS verification_status,
    (resource ->> 'recordedDate')::timestamptz                               AS recorded_at,
    resource -> 'reaction' -> 0 -> 'manifestation' -> 0 -> 'coding' -> 0 ->> 'display' AS reaction_description
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'AllergyIntolerance'
