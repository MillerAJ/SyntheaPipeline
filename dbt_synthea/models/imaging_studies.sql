{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS imaging_study_id,
    {{ fhir_id("resource -> 'subject' ->> 'reference'") }}                   AS patient_id,
    {{ fhir_id("resource -> 'encounter' ->> 'reference'") }}                 AS encounter_id,
    resource ->> 'status'                                                    AS status,
    (resource ->> 'started')::timestamptz                                    AS started_at,
    (resource ->> 'numberOfSeries')::int                                     AS number_of_series,
    (resource ->> 'numberOfInstances')::int                                  AS number_of_instances,
    resource -> 'procedureCode' -> 0 -> 'coding' -> 0 ->> 'code'             AS procedure_code,
    resource -> 'procedureCode' -> 0 -> 'coding' -> 0 ->> 'display'          AS procedure_description,
    resource -> 'series' -> 0 -> 'modality' ->> 'code'                       AS modality_code,
    resource -> 'series' -> 0 -> 'bodySite' ->> 'display'                    AS body_site,
    resource -> 'location' ->> 'display'                                     AS location_name,
    resource -> 'identifier' -> 0 ->> 'value'                                                        AS identifier_value,
    resource -> 'location' ->> 'reference'                                                           AS location_reference,
    resource -> 'procedureCode' -> 0 ->> 'text'                                                      AS procedure_text,
    resource -> 'series' -> 0 -> 'modality' ->> 'display'                                            AS modality_display,
    resource -> 'series' -> 0 -> 'bodySite' ->> 'code'                                               AS body_site_code,
    resource -> 'series' -> 0 ->> 'uid'                                                              AS series_uid,
    (resource -> 'series' -> 0 ->> 'started')::timestamptz                                           AS series_started_at
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'ImagingStudy'
