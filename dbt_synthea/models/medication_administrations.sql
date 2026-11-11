{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS medication_administration_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'context' ->> 'reference'") }}                   AS encounter_id,
    resource ->> 'status'                                                    AS status,
    resource -> 'medicationCodeableConcept' -> 'coding' -> 0 ->> 'code'      AS medication_code,
    resource -> 'medicationCodeableConcept' -> 'coding' -> 0 ->> 'display'   AS medication_description,
    (resource ->> 'effectiveDateTime')::timestamptz                          AS effective_at,
    coalesce(resource -> 'reasonReference' -> 0 ->> 'display',
             resource -> 'reasonCode' -> 0 -> 'coding' -> 0 ->> 'display')   AS reason_description
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'MedicationAdministration'
