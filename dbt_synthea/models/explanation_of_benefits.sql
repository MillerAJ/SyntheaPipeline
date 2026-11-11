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
    jsonb_array_length(resource -> 'item')                                   AS item_count
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'ExplanationOfBenefit'
