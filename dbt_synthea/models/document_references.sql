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
    convert_from(decode(resource -> 'content' -> 0 -> 'attachment' ->> 'data', 'base64'), 'UTF8') AS note_text
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'DocumentReference'
