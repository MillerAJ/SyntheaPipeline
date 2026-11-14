{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS care_plan_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'encounter' ->> 'reference'") }}                 AS encounter_id,
    {{ fhir_id("resource -> 'careTeam' -> 0 ->> 'reference'") }}             AS care_team_id,
    resource ->> 'status'                                                    AS status,
    resource ->> 'intent'                                                    AS intent,
    resource -> 'category' -> 0 -> 'coding' -> 0 ->> 'code'                  AS category_code,
    (resource -> 'period' ->> 'start')::timestamptz                          AS start_at,
    (resource -> 'period' ->> 'end')::timestamptz                            AS end_at,
    jsonb_array_length(resource -> 'activity')                               AS activity_count,
    jsonb_array_length(resource -> 'addresses')                              AS addressed_condition_count,
    (SELECT c ->> 'display' FROM jsonb_array_elements(resource -> 'category') AS cat, jsonb_array_elements(cat -> 'coding') AS c WHERE c ->> 'display' IS NOT NULL LIMIT 1) AS category_display,
    (SELECT cat ->> 'text' FROM jsonb_array_elements(resource -> 'category') AS cat WHERE cat ->> 'text' IS NOT NULL LIMIT 1) AS category_text,
    {{ fhir_id("resource -> 'addresses' -> 0 ->> 'reference'") }}                                    AS addressed_condition_id
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'CarePlan'
