{{ config(materialized='table', schema='flat') }}

SELECT
    r.id                                     AS raw_id,
    extract(epoch from r.loaded_at::timestamp)::bigint AS inserted_at,
    entry -> 'resource' ->> 'resourceType'   AS resource_type,
    entry -> 'resource'                      AS resource
FROM {{ source('raw_synthea_source', 'fhir_bundles') }} r,
     jsonb_array_elements(r.payload -> 'entry') AS entry
