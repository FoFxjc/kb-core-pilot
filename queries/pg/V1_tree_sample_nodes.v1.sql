-- Primary-tree nodes of one document for the tree spot check (D22).
SELECT node_id, parent_id, ord, title, origin, start_page, end_page, page_label_range
FROM content.node
WHERE doc_id = %(doc_id)s AND is_primary
ORDER BY ord
