-- Regions of one page in reading order, with their node (document view overlays).
SELECT region_id, type, subtype, layer, reading_order, bbox, text, table_id, node_id
FROM content.region
WHERE doc_id = %(doc_id)s AND page_no = %(page_no)s
ORDER BY reading_order
