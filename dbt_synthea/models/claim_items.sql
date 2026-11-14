{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS claim_id,
    {{ fhir_id("b.resource -> 'patient' ->> 'reference'") }}                                         AS patient_id,
    {{ fhir_id("i.item -> 'encounter' -> 0 ->> 'reference'") }}                                      AS encounter_id,
    (i.item ->> 'sequence')::int                                                                     AS item_sequence,
    i.item -> 'productOrService' -> 'coding' -> 0 ->> 'code'                                         AS product_code,
    i.item -> 'productOrService' -> 'coding' -> 0 ->> 'display'                                      AS product_description,
    (i.item -> 'net' ->> 'value')::numeric                                                           AS net_amount,
    i.item -> 'net' ->> 'currency'                                                                   AS currency,
    i.item -> 'diagnosisSequence' ->> 0                                                              AS diagnosis_sequence,
    i.item -> 'procedureSequence' ->> 0                                                              AS procedure_sequence,
    i.item -> 'informationSequence' ->> 0                                                            AS information_sequence
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'item') AS i(item)
WHERE b.resource_type = 'Claim'
