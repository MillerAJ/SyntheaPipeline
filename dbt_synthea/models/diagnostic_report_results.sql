{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS diagnostic_report_id,
    {{ fhir_id("b.resource -> 'subject' ->> 'reference'") }}                                         AS patient_id,
    {{ fhir_id("b.resource -> 'encounter' ->> 'reference'") }}                                       AS encounter_id,
    r.seq::int                                                                                       AS result_seq,
    {{ fhir_id("r.res ->> 'reference'") }}                                                           AS observation_id,
    r.res ->> 'display'                                                                              AS observation_description
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'result') WITH ORDINALITY AS r(res, seq)
WHERE b.resource_type = 'DiagnosticReport'
