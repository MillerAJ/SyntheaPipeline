{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS claim_id,
    {{ fhir_id("resource -> 'patient' ->> 'reference'") }}                   AS patient_id,
    resource ->> 'status'                                                    AS status,
    resource ->> 'use'                                                       AS use_type,
    resource -> 'type' -> 'coding' -> 0 ->> 'code'                           AS claim_type,
    resource -> 'priority' -> 'coding' -> 0 ->> 'code'                       AS priority,
    (resource ->> 'created')::timestamptz                                    AS created_at,
    (resource -> 'billablePeriod' ->> 'start')::timestamptz                  AS billable_start_at,
    (resource -> 'billablePeriod' ->> 'end')::timestamptz                    AS billable_end_at,
    (resource -> 'total' ->> 'value')::numeric                               AS total_amount,
    resource -> 'total' ->> 'currency'                                       AS currency,
    resource -> 'provider' ->> 'display'                                     AS provider_name,
    resource -> 'provider' ->> 'reference'                                   AS provider_reference,
    resource -> 'facility' ->> 'display'                                     AS facility_name,
    resource -> 'facility' ->> 'reference'                                   AS facility_reference,
    jsonb_array_length(resource -> 'item')                                   AS item_count
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Claim'
