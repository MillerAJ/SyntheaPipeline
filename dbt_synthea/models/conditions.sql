{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS condition_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'encounter' ->> 'reference'") }}                 AS encounter_id,
    resource -> 'clinicalStatus' -> 'coding' -> 0 ->> 'code'                 AS clinical_status,
    resource -> 'verificationStatus' -> 'coding' -> 0 ->> 'code'             AS verification_status,
    resource -> 'category' -> 0 -> 'coding' -> 0 ->> 'code'                  AS category_code,
    resource -> 'code' -> 'coding' -> 0 ->> 'code'                           AS code,
    resource -> 'code' -> 'coding' -> 0 ->> 'display'                        AS description,
    (resource ->> 'onsetDateTime')::timestamptz                              AS onset_at,
    (resource ->> 'abatementDateTime')::timestamptz                          AS abatement_at,
    (resource ->> 'recordedDate')::timestamptz                               AS recorded_at
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Condition'
