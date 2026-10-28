-- Page documents for the ES page index (design §4.2); reindex reads Postgres only. Round 2 W3: the effective
-- access label flattened into access_* fields for the route filters.
SELECT doc_id, page_no, page_label, fiscal_year, lang, issuer, text, text_tok,
       access->>'classification' AS access_classification,
       ARRAY(SELECT jsonb_array_elements_text(coalesce(access->'domains', '[]'::jsonb))) AS access_domains,
       access->>'embargo_until' AS access_embargo_until
FROM content.page
WHERE {filters}
ORDER BY doc_id, page_no
