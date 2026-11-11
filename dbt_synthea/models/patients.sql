{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                    AS patient_id,
    resource ->> 'gender'                                                AS gender,
    (resource ->> 'birthDate')::date                                     AS birth_date,
    (resource ->> 'deceasedDateTime')::timestamptz                       AS deceased_at,
    (resource -> 'deceasedDateTime') IS NOT NULL                         AS is_deceased,
    resource -> 'maritalStatus' -> 'coding' -> 0 ->> 'code'              AS marital_status_code,
    resource -> 'name' -> 0 -> 'prefix' ->> 0                            AS name_prefix,
    (SELECT string_agg(g, ' ')
       FROM jsonb_array_elements_text(resource -> 'name' -> 0 -> 'given') AS g) AS given_names,
    resource -> 'name' -> 0 ->> 'family'                                 AS family_name,
    resource -> 'telecom' -> 0 ->> 'value'                               AS phone,
    resource -> 'address' -> 0 -> 'line' ->> 0                           AS address_line,
    resource -> 'address' -> 0 ->> 'city'                                AS city,
    resource -> 'address' -> 0 ->> 'state'                               AS state,
    resource -> 'address' -> 0 ->> 'postalCode'                          AS postal_code,
    resource -> 'address' -> 0 ->> 'country'                             AS country,
    (resource -> 'address' -> 0 -> 'extension' -> 0 -> 'extension' -> 0 ->> 'valueDecimal')::numeric AS latitude,
    (resource -> 'address' -> 0 -> 'extension' -> 0 -> 'extension' -> 1 ->> 'valueDecimal')::numeric AS longitude,
    (SELECT e -> 'extension' -> 0 -> 'valueCoding' ->> 'display'
       FROM jsonb_array_elements(resource -> 'extension') AS e
      WHERE e ->> 'url' = 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-race')      AS race,
    (SELECT e -> 'extension' -> 0 -> 'valueCoding' ->> 'display'
       FROM jsonb_array_elements(resource -> 'extension') AS e
      WHERE e ->> 'url' = 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity') AS ethnicity,
    (SELECT e ->> 'valueCode'
       FROM jsonb_array_elements(resource -> 'extension') AS e
      WHERE e ->> 'url' = 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-birthsex')  AS birth_sex,
    (resource ->> 'multipleBirthBoolean')::boolean                       AS multiple_birth,
    (resource ->> 'multipleBirthInteger')::int                           AS multiple_birth_order
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Patient'
