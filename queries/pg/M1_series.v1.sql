-- M1 series (api-contract §5.5): fact versions of a concept for all years of the given entities, with the
-- representative observation (provenance).
SELECT f.fact_id, f.entity_id, f.fiscal_year, f.period_id, f.unit, f.restated_note, v.version_no, v.known_from,
       v.known_to, v.value, v.status, v.n_sources, o.doc_id, o.table_id, o.row_label, o.page_no, o.page_label,
       o.raw_value, o.raw_scale, o.snippet
FROM fact.fact f
JOIN fact.fact_version v ON v.fact_id = f.fact_id
JOIN fact.observation o ON o.obs_id = v.winning_obs_id
WHERE f.concept_id = %(concept_id)s AND f.entity_id = ANY(%(entities)s)
ORDER BY f.fiscal_year, v.version_no
