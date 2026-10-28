-- The registered document a build reads: its package in the store, its declared metadata and its access label.
SELECT doc_id, issuer_id, doc_type, fiscal_year, lang, package, manifest, access
FROM registry.document
WHERE doc_id = %(doc_id)s
