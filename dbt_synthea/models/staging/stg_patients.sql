SELECT
    resource ->> 'id'                                       AS patient_id,
    resource -> 'name' -> 0 ->> 'family'                    AS last_name,
    resource -> 'name' -> 0 -> 'given' ->> 0                AS first_name,
    resource ->> 'gender'                                   AS gender,
    (resource ->> 'birthDate')::date                        AS birth_date,
    resource -> 'address' -> 0 ->> 'city'                   AS city,
    resource -> 'address' -> 0 ->> 'state'                  AS state,
    resource -> 'address' -> 0 ->> 'postalCode'             AS postal_code,
    resource -> 'maritalStatus' -> 'coding' -> 0 ->> 'display' AS marital_status
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Patient'
