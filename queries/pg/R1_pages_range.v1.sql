-- read: pages of one document in a physical page range.
SELECT page_no, page_label, page_label_source, text, covering_node_ids
FROM content.page
WHERE doc_id = %(doc_id)s AND page_no BETWEEN %(start)s AND %(end)s
ORDER BY page_no
