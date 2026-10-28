INSERT INTO registry.document (doc_id, issuer_id, doc_type, period_end, fiscal_year, lang, source_url, completeness,
    translation_of, publisher, published_at, page_count, has_text_layer, package, package_sha256, contract_version,
    manifest, access)
VALUES (%(doc_id)s, %(issuer_id)s, %(doc_type)s, %(period_end)s, %(fiscal_year)s, %(lang)s, %(source_url)s,
    %(completeness)s, %(translation_of)s, %(publisher)s, %(published_at)s, %(page_count)s, %(has_text_layer)s,
    %(package)s, %(package_sha256)s, %(contract_version)s, %(manifest)s, %(access)s)
