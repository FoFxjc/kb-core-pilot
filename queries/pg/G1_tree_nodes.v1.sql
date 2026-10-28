-- All primary-tree nodes (catalog trees; browse, local outlines and page-to-node mapping read only the cache).
SELECT doc_id, node_id, parent_id, depth, ord, title, summary, start_page, end_page, page_label_range, tree_source,
       section_type, section_rule, is_primary
FROM content.node
WHERE is_primary
ORDER BY doc_id, ord
