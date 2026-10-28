INSERT INTO content.table_block (doc_id, table_id, region_id, node_id, page_start, page_end, bbox, n_rows, n_cols,
    caption, unit_hint, markdown, extract_method, table_kind, cells, parsed, continued_hint)
VALUES (%(doc_id)s, %(table_id)s, %(region_id)s, %(node_id)s, %(page_start)s, %(page_end)s, %(bbox)s, %(n_rows)s,
    %(n_cols)s, %(caption)s, %(unit_hint)s, %(markdown)s, %(extract_method)s, %(table_kind)s, %(cells)s, %(parsed)s,
    %(continued_hint)s)
