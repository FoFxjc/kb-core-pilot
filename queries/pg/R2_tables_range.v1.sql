-- read: tables starting in a physical page range.
SELECT table_id, page_start, markdown
FROM content.table_block
WHERE doc_id = %(doc_id)s AND page_start BETWEEN %(start)s AND %(end)s
ORDER BY page_start, table_id
