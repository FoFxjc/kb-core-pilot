-- M7 (round 2 W3): every observation of a concept for the given entities, with the access labels of its document and
-- table, so facts can be recomputed from the observations the subject may see.
SELECT o.obs_id, o.doc_id, o.report_year, o.concept_id, o.entity_id, o.fiscal_year, o.period_id, o.value, o.unit,
       o.restated_note, o.table_id, o.row_label, o.page_no, o.page_label, o.raw_value, o.raw_scale, o.snippet,
       d.access AS doc_access, t.access AS table_access
FROM fact.observation o
JOIN registry.document d ON d.doc_id = o.doc_id
LEFT JOIN content.table_block t ON t.table_id = o.table_id
WHERE o.concept_id = %(concept_id)s AND o.entity_id = ANY(%(entities)s)
ORDER BY o.obs_id
