{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS procedure_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'encounter' ->> 'reference'") }}                 AS encounter_id,
    resource ->> 'status'                                                    AS status,
    resource -> 'code' -> 'coding' -> 0 ->> 'code'                           AS code,
    resource -> 'code' -> 'coding' -> 0 ->> 'display'                        AS description,
    (resource -> 'performedPeriod' ->> 'start')::timestamptz                 AS performed_start_at,
    (resource -> 'performedPeriod' ->> 'end')::timestamptz                   AS performed_end_at,
    resource -> 'location' ->> 'display'                                     AS location_name,
    resource -> 'reasonReference' -> 0 ->> 'display'                         AS reason_description
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Procedure'
