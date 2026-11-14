{{ config(materialized='table', schema='flat') }}

SELECT
    raw_id,
    inserted_at,
    resource ->> 'id'                                                        AS supply_delivery_id,
    {{ fhir_id("resource -> 'patient' ->> 'reference'") }}                   AS patient_id,
    resource ->> 'status'                                                    AS status,
    resource -> 'type' -> 'coding' -> 0 ->> 'code'                           AS type_code,
    resource -> 'suppliedItem' -> 'itemCodeableConcept' -> 'coding' -> 0 ->> 'code'    AS item_code,
    resource -> 'suppliedItem' -> 'itemCodeableConcept' -> 'coding' -> 0 ->> 'display' AS item_description,
    (resource -> 'suppliedItem' -> 'quantity' ->> 'value')::numeric          AS quantity,
    (resource ->> 'occurrenceDateTime')::timestamptz                         AS occurrence_at,
    resource -> 'type' -> 'coding' -> 0 ->> 'display'                                                AS type_display,
    resource -> 'suppliedItem' -> 'itemCodeableConcept' ->> 'text'                                   AS item_text
FROM {{ ref('base_synthea_entries') }}
WHERE resource_type = 'SupplyDelivery'
