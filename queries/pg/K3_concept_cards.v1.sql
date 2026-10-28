SELECT c.concept_id, c.name_en, c.name_zh, c.value_type, c.aggregation,
       coalesce((SELECT json_agg(a.alias ORDER BY a.alias) FROM concept.concept_alias a
                 WHERE a.concept_id = c.concept_id AND a.lang = 'en'), '[]') AS aliases_en,
       coalesce((SELECT json_agg(a.alias ORDER BY a.alias) FROM concept.concept_alias a
                 WHERE a.concept_id = c.concept_id AND a.lang = 'zh'), '[]') AS aliases_zh,
       (SELECT count(*) FROM concept.node_concept n WHERE n.concept_id = c.concept_id) AS node_count
FROM concept.concept c
WHERE c.concept_id = ANY(%(ids)s)
