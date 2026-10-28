-- Digest of one document's interpretation rows (run times excluded): a rebuild of the same package with the same
-- configuration must give the same digest (design §3).
SELECT md5(concat_ws('|',
    (SELECT string_agg(to_jsonb(n)::text, E'\n' ORDER BY n.node_id) FROM content.node n WHERE n.doc_id = %(doc_id)s),
    (SELECT string_agg(to_jsonb(p)::text, E'\n' ORDER BY p.page_no) FROM content.page p WHERE p.doc_id = %(doc_id)s),
    (SELECT string_agg(to_jsonb(r)::text, E'\n' ORDER BY r.region_id) FROM content.region r WHERE r.doc_id = %(doc_id)s),
    (SELECT string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.table_id) FROM content.table_block t WHERE t.doc_id = %(doc_id)s),
    (SELECT string_agg(to_jsonb(m)::text, E'\n' ORDER BY m.merge_id) FROM content.table_merge m WHERE m.doc_id = %(doc_id)s),
    (SELECT string_agg(to_jsonb(c)::text, E'\n' ORDER BY c.node_id, c.concept_id) FROM concept.node_concept c
        WHERE c.doc_id = %(doc_id)s)))
