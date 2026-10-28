-- Page documents for the ES page index (design §4.2); reindex reads Postgres only.
SELECT doc_id, page_no, page_label, fiscal_year, lang, issuer, text, text_tok
FROM content.page
WHERE {filters}
ORDER BY doc_id, page_no
