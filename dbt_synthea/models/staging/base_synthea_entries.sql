{{ config(materialized='table', schema='flat') }}

SELECT
    r.id                                    AS raw_id,
    r.inserted_at,
    entry -> 'resource' ->> 'resourceType'  AS resource_type,
    entry -> 'resource'                     AS resource
FROM {{ source('raw_synthea_source', 'raw_synthea') }} r,
     jsonb_array_elements(r.payload -> 'entry') AS entry
