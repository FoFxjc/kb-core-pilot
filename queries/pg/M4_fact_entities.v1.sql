-- entities with facts for some concepts (issuer choice for get_metric_series)
SELECT DISTINCT entity_id FROM fact.fact WHERE concept_id = ANY(%(ids)s) ORDER BY entity_id
