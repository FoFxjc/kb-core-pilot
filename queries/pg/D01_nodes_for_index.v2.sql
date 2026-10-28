-- Node documents for the ES node index (design §4.2); reindex reads Postgres only. Round 2 W3: the effective
-- access label flattened into access_* fields for the route filters.
SELECT node_id, doc_id, parent_id, fiscal_year, lang, issuer, section_type, tree_source, is_primary, depth, ord,
       start_page, end_page, title, title_tok, summary_tok, concept_tok,
       access->>'classification' AS access_classification,
       ARRAY(SELECT jsonb_array_elements_text(coalesce(access->'domains', '[]'::jsonb))) AS access_domains,
       access->>'embargo_until' AS access_embargo_until
FROM content.node
WHERE {filters}
ORDER BY doc_id, ord
