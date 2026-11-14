{{ config(materialized='table', schema='flat') }}

SELECT
    b.raw_id,
    b.inserted_at,
    b.resource ->> 'id'                                                                              AS medication_request_id,
    {{ fhir_id("b.resource -> 'subject' ->> 'reference'") }}                                         AS patient_id,
    (d.dose ->> 'sequence')::int                                                                     AS dosage_sequence,
    d.dose ->> 'text'                                                                                AS dosage_text,
    (d.dose ->> 'asNeededBoolean')::boolean                                                          AS as_needed,
    (d.dose -> 'doseAndRate' -> 0 -> 'doseQuantity' ->> 'value')::numeric                            AS dose_value,
    d.dose -> 'doseAndRate' -> 0 -> 'type' -> 'coding' -> 0 ->> 'code'                               AS dose_type_code,
    (d.dose -> 'timing' -> 'repeat' ->> 'frequency')::int                                            AS frequency,
    (d.dose -> 'timing' -> 'repeat' ->> 'period')::numeric                                           AS period,
    d.dose -> 'timing' -> 'repeat' ->> 'periodUnit'                                                  AS period_unit,
    d.dose -> 'additionalInstruction' -> 0 -> 'coding' -> 0 ->> 'code'                               AS additional_instruction_code,
    d.dose -> 'additionalInstruction' -> 0 ->> 'text'                                                AS additional_instruction_text
FROM {{ ref('base_synthea_entries') }} AS b
CROSS JOIN LATERAL jsonb_array_elements(b.resource -> 'dosageInstruction') AS d(dose)
WHERE b.resource_type = 'MedicationRequest'
