{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS eob_id,
    {{ fhir_id("b.resource -> 'claim' ->> 'reference'") }}                                           AS claim_id,
    {{ fhir_id("b.resource -> 'patient' ->> 'reference'") }}                                         AS patient_id,
    {{ fhir_id("i.item -> 'encounter' -> 0 ->> 'reference'") }}                                      AS encounter_id,
    (i.item ->> 'sequence')::int                                                                     AS item_sequence,
    i.item -> 'category' -> 'coding' -> 0 ->> 'code'                                                 AS category_code,
    i.item -> 'category' -> 'coding' -> 0 ->> 'display'                                              AS category_display,
    i.item -> 'productOrService' -> 'coding' -> 0 ->> 'code'                                         AS product_code,
    i.item -> 'productOrService' -> 'coding' -> 0 ->> 'display'                                      AS product_description,
    i.item -> 'locationCodeableConcept' -> 'coding' -> 0 ->> 'code'                                  AS location_code,
    i.item -> 'locationCodeableConcept' -> 'coding' -> 0 ->> 'display'                               AS location_display,
    (i.item -> 'servicedPeriod' ->> 'start')::timestamptz                                            AS serviced_start_at,
    (i.item -> 'servicedPeriod' ->> 'end')::timestamptz                                              AS serviced_end_at,
    (i.item -> 'net' ->> 'value')::numeric                                                           AS net_amount,
    i.item -> 'net' ->> 'currency'                                                                   AS currency,
    i.item -> 'diagnosisSequence' ->> 0                                                              AS diagnosis_sequence,
    i.item -> 'informationSequence' ->> 0                                                            AS information_sequence,
    jsonb_array_length(i.item -> 'adjudication')                                                     AS adjudication_count
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'item') AS i(item)
WHERE b.resource_type = 'ExplanationOfBenefit'
