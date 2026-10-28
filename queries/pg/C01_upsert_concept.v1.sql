INSERT INTO concept.concept (concept_id, name_en, name_zh, value_type, aggregation, default_period_kind, definition,
    derive, spec_version)
VALUES (%(concept_id)s, %(name_en)s, %(name_zh)s, %(value_type)s, %(aggregation)s, %(default_period_kind)s,
    %(definition)s, %(derive)s, %(spec_version)s)
ON CONFLICT (concept_id) DO UPDATE SET name_en = EXCLUDED.name_en, name_zh = EXCLUDED.name_zh,
    value_type = EXCLUDED.value_type, aggregation = EXCLUDED.aggregation,
    default_period_kind = EXCLUDED.default_period_kind, definition = EXCLUDED.definition, derive = EXCLUDED.derive,
    spec_version = EXCLUDED.spec_version
