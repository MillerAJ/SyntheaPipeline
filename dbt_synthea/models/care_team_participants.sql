{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS care_team_id,
    {{ fhir_id("b.resource -> 'subject' ->> 'reference'") }}                                         AS patient_id,
    {{ fhir_id("b.resource -> 'encounter' ->> 'reference'") }}                                       AS encounter_id,
    p.seq::int                                                                                       AS participant_seq,
    p.part -> 'role' -> 0 -> 'coding' -> 0 ->> 'code'                                                AS role_code,
    p.part -> 'role' -> 0 -> 'coding' -> 0 ->> 'display'                                             AS role_display,
    p.part -> 'member' ->> 'display'                                                                 AS member_name,
    p.part -> 'member' ->> 'reference'                                                               AS member_reference
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'participant') WITH ORDINALITY AS p(part, seq)
WHERE b.resource_type = 'CareTeam'
