{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS imaging_study_id,
    {{ fhir_id("b.resource -> 'subject' ->> 'reference'") }}                                         AS patient_id,
    (s.ser ->> 'number')::int                                                                        AS series_number,
    s.ser ->> 'uid'                                                                                  AS series_uid,
    (s.ser ->> 'started')::timestamptz                                                               AS series_started_at,
    (s.ser ->> 'numberOfInstances')::int                                                             AS series_instance_count,
    s.ser -> 'modality' ->> 'code'                                                                   AS modality_code,
    s.ser -> 'modality' ->> 'display'                                                                AS modality_display,
    s.ser -> 'bodySite' ->> 'code'                                                                   AS body_site_code,
    s.ser -> 'bodySite' ->> 'display'                                                                AS body_site_display,
    (i.inst ->> 'number')::int                                                                       AS instance_number,
    i.inst ->> 'uid'                                                                                 AS instance_uid,
    i.inst ->> 'title'                                                                               AS instance_title,
    i.inst -> 'sopClass' ->> 'code'                                                                  AS sop_class_code
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'series') AS s(ser)
LEFT JOIN LATERAL jsonb_array_elements(s.ser -> 'instance') AS i(inst) ON TRUE
WHERE b.resource_type = 'ImagingStudy'
