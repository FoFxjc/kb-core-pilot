-- Node documents for the ES node index (design §4.2); reindex reads Postgres only.
SELECT node_id, doc_id, parent_id, fiscal_year, lang, issuer, section_type, tree_source, is_primary, depth, ord,
       start_page, end_page, title, title_tok, summary_tok, concept_tok
FROM content.node
WHERE {filters}
ORDER BY doc_id, ord
