SELECT
    resource ->> 'id'                                                     AS observation_id,
    split_part(resource -> 'subject' ->> 'reference', '/', 2)             AS patient_id,
    split_part(resource -> 'encounter' ->> 'reference', '/', 2)           AS encounter_id,
    resource -> 'code' -> 'coding' -> 0 ->> 'code'                        AS observation_code,
    resource -> 'code' -> 'coding' -> 0 ->> 'display'                     AS observation_name,
    resource -> 'valueQuantity' ->> 'value'                               AS value_numeric,
    resource -> 'valueQuantity' ->> 'unit'                                AS value_unit,
    resource -> 'valueCodeableConcept' -> 'coding' -> 0 ->> 'display'     AS value_text,
    resource ->> 'status'                                                 AS status,
    (resource ->> 'effectiveDateTime')::timestamptz                      AS effective_datetime
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Observation'
