INSERT INTO content.node (doc_id, node_id, parent_id, ancestors, depth, ord, title, title_tok, summary, summary_tok,
    start_page, end_page, page_label_range, tree_source, origin, is_primary, section_type, section_rule, fiscal_year,
    lang, issuer, concept_ids, concept_tok, region_ids, access)
VALUES (%(doc_id)s, %(node_id)s, %(parent_id)s, %(ancestors)s, %(depth)s, %(ord)s, %(title)s, %(title_tok)s,
    %(summary)s, %(summary_tok)s, %(start_page)s, %(end_page)s, %(page_label_range)s, %(tree_source)s, %(origin)s,
    %(is_primary)s, %(section_type)s, %(section_rule)s, %(fiscal_year)s, %(lang)s, %(issuer)s, %(concept_ids)s,
    %(concept_tok)s, %(region_ids)s, %(access)s)
