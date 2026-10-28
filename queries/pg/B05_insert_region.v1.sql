INSERT INTO content.region (doc_id, region_id, page_no, bbox, type, subtype, layer, reading_order, text, font, status,
    table_id, node_id)
VALUES (%(doc_id)s, %(region_id)s, %(page_no)s, %(bbox)s, %(type)s, %(subtype)s, %(layer)s, %(reading_order)s,
    %(text)s, %(font)s, %(status)s, %(table_id)s, %(node_id)s)
