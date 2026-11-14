{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS eob_id,
    {{ fhir_id("b.resource -> 'claim' ->> 'reference'") }}                                           AS claim_id,
    {{ fhir_id("b.resource -> 'patient' ->> 'reference'") }}                                         AS patient_id,
    (i.item ->> 'sequence')::int                                                                     AS item_sequence,
    a.seq::int                                                                                       AS adjudication_seq,
    a.adj -> 'category' -> 'coding' -> 0 ->> 'code'                                                  AS category_code,
    a.adj -> 'category' -> 'coding' -> 0 ->> 'display'                                               AS category_display,
    (a.adj -> 'amount' ->> 'value')::numeric                                                         AS amount,
    a.adj -> 'amount' ->> 'currency'                                                                 AS currency
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'item') AS i(item)
CROSS JOIN LATERAL jsonb_array_elements(i.item -> 'adjudication') WITH ORDINALITY AS a(adj, seq)
WHERE b.resource_type = 'ExplanationOfBenefit'
