{{ config(materialized='table', schema='flat') }}

{# The base64 note in presentedForm is decoded into note_text and removed from resource to avoid storing it twice. #}
SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS diagnostic_report_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'encounter' ->> 'reference'") }}                 AS encounter_id,
    resource ->> 'status'                                                    AS status,
    resource -> 'category' -> 0 -> 'coding' -> 0 ->> 'code'                  AS category_code,
    resource -> 'code' -> 'coding' -> 0 ->> 'code'                           AS code,
    resource -> 'code' -> 'coding' -> 0 ->> 'display'                        AS description,
    (resource ->> 'effectiveDateTime')::timestamptz                          AS effective_at,
    (resource ->> 'issued')::timestamptz                                     AS issued_at,
    resource -> 'performer' -> 0 ->> 'display'                               AS performer_name,
    jsonb_array_length(resource -> 'result')                                 AS result_count,
    resource -> 'presentedForm' -> 0 ->> 'contentType'                       AS note_content_type,
    convert_from(decode(resource -> 'presentedForm' -> 0 ->> 'data', 'base64'), 'UTF8') AS note_text,
    resource -> 'code' ->> 'text'                                                                    AS code_text,
    resource -> 'category' -> 0 -> 'coding' -> 0 ->> 'display'                                       AS category_display,
    resource -> 'performer' -> 0 ->> 'reference'                                                     AS performer_reference,
    jsonb_array_length(resource -> 'performer')                                                      AS performer_count
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'DiagnosticReport'
