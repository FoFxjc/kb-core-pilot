-- years with facts per concept (availability)
SELECT concept_id, array_agg(DISTINCT fiscal_year ORDER BY fiscal_year) AS years
FROM fact.fact WHERE concept_id = ANY(%(ids)s) GROUP BY concept_id
