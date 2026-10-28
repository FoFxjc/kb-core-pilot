-- Tagged primary-tree nodes of documents in one language, with their tags (concept-tag spot check, kb D39).
SELECT n.doc_id, n.node_id, n.ord, n.title, n.start_page, n.end_page, n.page_label_range,
       json_agg(json_build_object('concept_id', nc.concept_id, 'name_en', c.name_en, 'method', nc.method,
                                  'variant', nc.variant) ORDER BY nc.concept_id) AS tags
FROM content.node n
JOIN concept.node_concept nc USING (node_id)
JOIN concept.concept c ON c.concept_id = nc.concept_id
WHERE n.lang = %(lang)s AND n.is_primary
GROUP BY n.doc_id, n.node_id, n.ord, n.title, n.start_page, n.end_page, n.page_label_range
ORDER BY n.doc_id, n.ord
