SELECT
    resource ->> 'id'                                                     AS condition_id,
    split_part(resource -> 'subject' ->> 'reference', '/', 2)             AS patient_id,
    split_part(resource -> 'encounter' ->> 'reference', '/', 2)           AS encounter_id,
    resource -> 'code' -> 'coding' -> 0 ->> 'code'                        AS condition_code,
    resource -> 'code' -> 'coding' -> 0 ->> 'display'                     AS condition_display,
    resource -> 'clinicalStatus' -> 'coding' -> 0 ->> 'code'              AS clinical_status,
    (resource ->> 'onsetDateTime')::timestamptz                          AS onset_datetime,
    (resource ->> 'abatementDateTime')::timestamptz                      AS abatement_datetime
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Condition'
