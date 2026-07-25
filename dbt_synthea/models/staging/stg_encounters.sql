SELECT
    resource ->> 'id'                                                     AS encounter_id,
    split_part(resource -> 'subject' ->> 'reference', '/', 2)             AS patient_id,
    resource -> 'class' ->> 'code'                                        AS encounter_class,
    resource -> 'type' -> 0 -> 'coding' -> 0 ->> 'code'                   AS encounter_type_code,
    resource -> 'type' -> 0 -> 'coding' -> 0 ->> 'display'                AS encounter_type,
    resource ->> 'status'                                                 AS status,
    (resource -> 'period' ->> 'start')::timestamptz                       AS period_start,
    (resource -> 'period' ->> 'end')::timestamptz                         AS period_end,
    split_part(resource -> 'serviceProvider' ->> 'reference', '/', 2)     AS organization_id
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Encounter'
