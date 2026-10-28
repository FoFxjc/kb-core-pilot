INSERT INTO content.page (doc_id, page_no, page_label, page_label_source, kind, excluded, width, height, fiscal_year,
    lang, issuer, text, text_tok, covering_node_ids, access)
VALUES (%(doc_id)s, %(page_no)s, %(page_label)s, %(page_label_source)s, %(kind)s, %(excluded)s, %(width)s, %(height)s,
    %(fiscal_year)s, %(lang)s, %(issuer)s, %(text)s, %(text_tok)s, %(covering_node_ids)s, %(access)s)
