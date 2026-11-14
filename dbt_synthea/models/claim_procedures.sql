{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS claim_id,
    {{ fhir_id("b.resource -> 'patient' ->> 'reference'") }}                                         AS patient_id,
    (p.pr ->> 'sequence')::int                                                                       AS procedure_sequence,
    {{ fhir_id("p.pr -> 'procedureReference' ->> 'reference'") }}                                    AS procedure_id
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'procedure') AS p(pr)
WHERE b.resource_type = 'Claim'
