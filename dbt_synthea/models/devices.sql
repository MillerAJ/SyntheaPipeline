{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS device_id,
    {{ fhir_id("resource -> 'patient' ->> 'reference'") }}                   AS patient_id,
    resource ->> 'status'                                                    AS status,
    resource -> 'type' -> 'coding' -> 0 ->> 'code'                           AS type_code,
    resource -> 'type' -> 'coding' -> 0 ->> 'display'                        AS type_description,
    resource -> 'deviceName' -> 0 ->> 'name'                                 AS device_name,
    resource ->> 'lotNumber'                                                 AS lot_number,
    resource ->> 'serialNumber'                                              AS serial_number,
    resource -> 'udiCarrier' -> 0 ->> 'deviceIdentifier'                     AS udi_device_identifier,
    (resource ->> 'manufactureDate')::timestamptz                            AS manufactured_at,
    (resource ->> 'expirationDate')::timestamptz                             AS expires_at
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'Device'
