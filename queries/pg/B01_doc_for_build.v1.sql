-- The registered document a build reads: its package in the store and its declared metadata.
SELECT doc_id, issuer_id, doc_type, fiscal_year, lang, package, manifest
FROM registry.document
WHERE doc_id = %(doc_id)s
