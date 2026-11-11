{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS medication_id,
    resource ->> 'status'                                                    AS status,
    resource -> 'code' -> 'coding' -> 0 ->> 'code'                           AS code,
    resource -> 'code' -> 'coding' -> 0 ->> 'display'                        AS description
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Medication'
