-- Documents the retrieval service knows (catalog): one row per built document, with its access label (round 2 W3).
SELECT d.doc_id, d.issuer_id, d.doc_type, d.period_end, d.fiscal_year, d.lang, d.source_url, d.completeness,
       d.translation_of, d.page_count,
       coalesce(d.manifest -> 'metadata' -> 'page_label_method' ->> 'method', 'none') AS page_label_source,
       (SELECT max(n.tree_source) FROM content.node n WHERE n.doc_id = d.doc_id) AS primary_tree_source, d.access
FROM registry.document d
WHERE d.status = 'built'
ORDER BY d.doc_id
