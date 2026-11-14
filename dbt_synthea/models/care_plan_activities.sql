{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS care_plan_id,
    {{ fhir_id("b.resource -> 'subject' ->> 'reference'") }}                                         AS patient_id,
    {{ fhir_id("b.resource -> 'encounter' ->> 'reference'") }}                                       AS encounter_id,
    a.seq::int                                                                                       AS activity_seq,
    a.act -> 'detail' ->> 'status'                                                                   AS status,
    a.act -> 'detail' -> 'code' -> 'coding' -> 0 ->> 'code'                                          AS code,
    a.act -> 'detail' -> 'code' -> 'coding' -> 0 ->> 'display'                                       AS description,
    a.act -> 'detail' -> 'location' ->> 'display'                                                    AS location_name,
    a.act -> 'detail' -> 'reasonCode' -> 0 -> 'coding' -> 0 ->> 'code'                               AS reason_code,
    a.act -> 'detail' -> 'reasonCode' -> 0 -> 'coding' -> 0 ->> 'display'                            AS reason_description,
    {{ fhir_id("a.act -> 'detail' -> 'reasonReference' -> 0 ->> 'reference'") }}                     AS reason_reference_id
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'activity') WITH ORDINALITY AS a(act, seq)
WHERE b.resource_type = 'CarePlan'
