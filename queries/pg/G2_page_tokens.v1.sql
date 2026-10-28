-- Page body tokens of every built page: document frequency for the coverage gate's IDF.
SELECT p.text_tok
FROM content.page p JOIN registry.document d USING (doc_id)
WHERE d.status = 'built'
