{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS encounter_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    resource ->> 'status'                                                    AS status,
    resource -> 'class' ->> 'code'                                           AS class_code,
    resource -> 'type' -> 0 -> 'coding' -> 0 ->> 'code'                      AS type_code,
    resource -> 'type' -> 0 -> 'coding' -> 0 ->> 'display'                   AS type_description,
    (resource -> 'period' ->> 'start')::timestamptz                          AS start_at,
    (resource -> 'period' ->> 'end')::timestamptz                            AS end_at,
    resource -> 'reasonCode' -> 0 -> 'coding' -> 0 ->> 'code'                AS reason_code,
    resource -> 'reasonCode' -> 0 -> 'coding' -> 0 ->> 'display'             AS reason_description,
    resource -> 'participant' -> 0 -> 'individual' ->> 'display'             AS primary_practitioner_name,
    resource -> 'participant' -> 0 -> 'individual' ->> 'reference'           AS primary_practitioner_reference,
    resource -> 'serviceProvider' ->> 'display'                              AS service_provider_name,
    resource -> 'serviceProvider' ->> 'reference'                            AS service_provider_reference,
    resource -> 'location' -> 0 -> 'location' ->> 'display'                  AS location_name,
    resource -> 'location' -> 0 -> 'location' ->> 'reference'                AS location_reference,
    resource -> 'subject' ->> 'display'                                                              AS patient_name,
    resource -> 'type' -> 0 ->> 'text'                                                               AS type_text,
    resource -> 'participant' -> 0 -> 'type' -> 0 -> 'coding' -> 0 ->> 'code'                        AS participant_type_code,
    resource -> 'participant' -> 0 -> 'type' -> 0 -> 'coding' -> 0 ->> 'display'                     AS participant_type_display,
    (resource -> 'participant' -> 0 -> 'period' ->> 'start')::timestamptz                            AS participant_start_at,
    (resource -> 'participant' -> 0 -> 'period' ->> 'end')::timestamptz                              AS participant_end_at,
    jsonb_array_length(resource -> 'participant')                                                    AS participant_count,
    resource -> 'hospitalization' -> 'dischargeDisposition' -> 'coding' -> 0 ->> 'code'              AS discharge_disposition_code,
    resource -> 'hospitalization' -> 'dischargeDisposition' -> 'coding' -> 0 ->> 'display'           AS discharge_disposition_display,
    jsonb_array_length(resource -> 'reasonCode')                                                     AS reason_count
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Encounter'
