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
    jsonb_array_length(resource -> 'item')                                   AS item_count,
    resource -> 'patient' ->> 'display'                                                              AS patient_name,
    resource -> 'insurance' -> 0 -> 'coverage' ->> 'display'                                         AS insurance_name,
    (resource -> 'insurance' -> 0 ->> 'focal')::boolean                                              AS insurance_focal,
    jsonb_array_length(resource -> 'insurance')                                                      AS insurance_count,
    {{ fhir_id("resource -> 'prescription' ->> 'reference'") }}                                      AS prescription_id,
    jsonb_array_length(resource -> 'diagnosis')                                                      AS diagnosis_count,
    jsonb_array_length(resource -> 'procedure')                                                      AS procedure_count,
    jsonb_array_length(resource -> 'supportingInfo')                                                 AS supporting_info_count,
    resource -> 'supportingInfo' -> 0 -> 'category' -> 'coding' -> 0 ->> 'code'                      AS supporting_info_category,
    {{ fhir_id("resource -> 'supportingInfo' -> 0 -> 'valueReference' ->> 'reference'") }}           AS supporting_info_reference_id
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Claim'
