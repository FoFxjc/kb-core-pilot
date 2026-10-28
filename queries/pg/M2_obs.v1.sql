-- M2 obs: all observations and roles of fact versions (include_obs, search fact provenance).
SELECT l.fact_id, l.version_no, l.role, o.obs_id, o.doc_id, o.report_year, o.table_id, o.page_no, o.page_label,
       o.row_label, o.value, o.raw_value, o.raw_scale, o.snippet
FROM fact.fact_obs_link l JOIN fact.observation o ON o.obs_id = l.obs_id
WHERE l.fact_id = ANY(%(fact_ids)s)
ORDER BY l.fact_id, l.version_no, o.report_year, o.doc_id, o.obs_id
