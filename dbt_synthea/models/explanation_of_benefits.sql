{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS eob_id,
    {{ fhir_id("resource -> 'patient' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'claim' ->> 'reference'") }}                     AS claim_id,
    resource ->> 'status'                                                    AS status,
    resource ->> 'use'                                                       AS use_type,
    resource ->> 'outcome'                                                   AS outcome,
    resource -> 'type' -> 'coding' -> 0 ->> 'code'                           AS eob_type,
    (resource ->> 'created')::timestamptz                                    AS created_at,
    (resource -> 'billablePeriod' ->> 'start')::timestamptz                  AS billable_start_at,
    (resource -> 'billablePeriod' ->> 'end')::timestamptz                    AS billable_end_at,
    resource -> 'insurer' ->> 'display'                                      AS insurer_name,
    resource -> 'provider' ->> 'reference'                                   AS provider_reference,
    resource -> 'facility' ->> 'display'                                     AS facility_name,
    (SELECT (t -> 'amount' ->> 'value')::numeric
       FROM jsonb_array_elements(resource -> 'total') AS t
      WHERE t -> 'category' -> 'coding' -> 0 ->> 'code' = 'submitted')       AS submitted_amount,
    (resource -> 'payment' -> 'amount' ->> 'value')::numeric                 AS payment_amount,
    resource -> 'payment' -> 'amount' ->> 'currency'                         AS currency,
    jsonb_array_length(resource -> 'item')                                   AS item_count,
    resource -> 'insurance' -> 0 -> 'coverage' ->> 'display'                                         AS insurer_coverage_name,
    (resource -> 'insurance' -> 0 ->> 'focal')::boolean                                              AS insurance_focal,
    resource -> 'facility' ->> 'reference'                                                           AS facility_reference,
    resource -> 'careTeam' -> 0 -> 'role' -> 'coding' -> 0 ->> 'code'                                AS care_team_role_code,
    resource -> 'careTeam' -> 0 -> 'role' -> 'coding' -> 0 ->> 'display'                             AS care_team_role_display,
    resource -> 'careTeam' -> 0 -> 'provider' ->> 'reference'                                        AS care_team_provider_reference,
    (SELECT c -> 'requester' ->> 'reference' FROM jsonb_array_elements(resource -> 'contained') AS c WHERE c ->> 'id' = 'referral') AS referral_requester_reference,
    (SELECT c ->> 'status' FROM jsonb_array_elements(resource -> 'contained') AS c WHERE c ->> 'id' = 'referral') AS referral_status,
    (SELECT c -> 'type' ->> 'text' FROM jsonb_array_elements(resource -> 'contained') AS c WHERE c ->> 'id' = 'coverage') AS coverage_type,
    (SELECT c ->> 'status' FROM jsonb_array_elements(resource -> 'contained') AS c WHERE c ->> 'id' = 'coverage') AS coverage_status,
    resource -> 'identifier' -> 0 ->> 'value'                                                        AS claim_identifier,
    jsonb_array_length(resource -> 'diagnosis')                                                      AS diagnosis_count,
    jsonb_array_length(resource -> 'total')                                                          AS total_count
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'ExplanationOfBenefit'
