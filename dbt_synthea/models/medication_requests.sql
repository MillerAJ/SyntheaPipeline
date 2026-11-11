{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS medication_request_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'encounter' ->> 'reference'") }}                 AS encounter_id,
    {{ fhir_id("resource -> 'medicationReference' ->> 'reference'") }}       AS medication_id,
    resource ->> 'status'                                                    AS status,
    resource ->> 'intent'                                                    AS intent,
    resource -> 'category' -> 0 -> 'coding' -> 0 ->> 'code'                  AS category_code,
    (resource ->> 'authoredOn')::timestamptz                                 AS authored_at,
    resource -> 'requester' ->> 'display'                                    AS requester_name,
    resource -> 'medicationCodeableConcept' -> 'coding' -> 0 ->> 'code'      AS medication_code,
    resource -> 'medicationCodeableConcept' -> 'coding' -> 0 ->> 'display'   AS medication_description,
    coalesce(resource -> 'reasonReference' -> 0 ->> 'display',
             resource -> 'reasonCode' -> 0 -> 'coding' -> 0 ->> 'display')   AS reason_description,
    (resource -> 'dosageInstruction' -> 0 -> 'doseAndRate' -> 0 -> 'doseQuantity' ->> 'value')::numeric AS dose_quantity,
    (resource -> 'dosageInstruction' -> 0 -> 'timing' -> 'repeat' ->> 'frequency')::int                AS dose_frequency,
    (resource -> 'dosageInstruction' -> 0 -> 'timing' -> 'repeat' ->> 'period')::numeric               AS dose_period,
    resource -> 'dosageInstruction' -> 0 -> 'timing' -> 'repeat' ->> 'periodUnit'                      AS dose_period_unit
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'MedicationRequest'
