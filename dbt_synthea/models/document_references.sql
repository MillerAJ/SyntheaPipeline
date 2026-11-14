{{ config(materialized='table', schema='flat') }}

{# The base64 note in content[0].attachment is decoded into note_text and removed from resource to avoid storing it twice. #}
SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS document_reference_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'context' -> 'encounter' -> 0 ->> 'reference'") }} AS encounter_id,
    resource ->> 'status'                                                    AS status,
    resource -> 'type' -> 'coding' -> 0 ->> 'code'                           AS type_code,
    resource -> 'type' -> 'coding' -> 0 ->> 'display'                        AS type_description,
    (resource ->> 'date')::timestamptz                                       AS document_at,
    resource -> 'author' -> 0 ->> 'display'                                  AS author_name,
    resource -> 'custodian' ->> 'display'                                    AS custodian_name,
    resource -> 'content' -> 0 -> 'attachment' ->> 'contentType'             AS content_type,
    convert_from(decode(resource -> 'content' -> 0 -> 'attachment' ->> 'data', 'base64'), 'UTF8') AS note_text,
    resource -> 'category' -> 0 -> 'coding' -> 0 ->> 'code'                                          AS category_code,
    resource -> 'category' -> 0 -> 'coding' -> 0 ->> 'display'                                       AS category_display,
    resource -> 'author' -> 0 ->> 'reference'                                                        AS author_reference,
    resource -> 'custodian' ->> 'reference'                                                          AS custodian_reference,
    resource -> 'content' -> 0 -> 'format' ->> 'code'                                                AS format_code,
    resource -> 'content' -> 0 -> 'format' ->> 'display'                                             AS format_display,
    (resource -> 'context' -> 'period' ->> 'start')::timestamptz                                     AS context_start_at,
    (resource -> 'context' -> 'period' ->> 'end')::timestamptz                                       AS context_end_at,
    resource -> 'identifier' -> 0 ->> 'value'                                                        AS identifier_value
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'DocumentReference'
