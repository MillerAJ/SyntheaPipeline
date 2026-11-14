{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS claim_id,
    {{ fhir_id("b.resource -> 'patient' ->> 'reference'") }}                                         AS patient_id,
    (d.dx ->> 'sequence')::int                                                                       AS diagnosis_sequence,
    {{ fhir_id("d.dx -> 'diagnosisReference' ->> 'reference'") }}                                    AS condition_id
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'diagnosis') AS d(dx)
WHERE b.resource_type = 'Claim'
