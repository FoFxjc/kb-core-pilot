-- Admin: every imported document with its build status, primary-tree source and tree spot-check accuracy.
SELECT d.doc_id, d.issuer_id, d.doc_type, d.fiscal_year, d.lang, d.page_count, d.package, d.contract_version, d.status,
       d.imported_at,
       (SELECT max(n.tree_source) FROM content.node n WHERE n.doc_id = d.doc_id) AS primary_tree_source,
       (SELECT c.value FROM quality.coverage c WHERE c.scope_type = 'document' AND c.scope_id = d.doc_id
                                               AND c.metric = 'tree_sample_accuracy') AS tree_sample_accuracy
FROM registry.document d
ORDER BY d.doc_id
