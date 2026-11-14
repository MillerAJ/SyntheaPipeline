{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS care_team_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'encounter' ->> 'reference'") }}                 AS encounter_id,
    resource ->> 'status'                                                    AS status,
    (resource -> 'period' ->> 'start')::timestamptz                          AS start_at,
    (resource -> 'period' ->> 'end')::timestamptz                            AS end_at,
    resource -> 'reasonCode' -> 0 -> 'coding' -> 0 ->> 'code'                AS reason_code,
    resource -> 'reasonCode' -> 0 -> 'coding' -> 0 ->> 'display'             AS reason_description,
    resource -> 'managingOrganization' -> 0 ->> 'display'                    AS managing_organization_name,
    jsonb_array_length(resource -> 'participant')                            AS participant_count,
    resource -> 'reasonCode' -> 0 ->> 'text'                                                         AS reason_text,
    resource -> 'managingOrganization' -> 0 ->> 'reference'                                          AS managing_organization_reference
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'CareTeam'
