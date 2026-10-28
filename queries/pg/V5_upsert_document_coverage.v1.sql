-- One document-level coverage metric (e.g. tree_sample_accuracy from a judged spot-check sheet); replaces the old row.
INSERT INTO quality.coverage (scope_type, scope_id, metric, numerator, denominator, value, config_version, computed_at)
VALUES ('document', %(doc_id)s, %(metric)s, %(numerator)s, %(denominator)s, %(value)s, %(config_version)s, now())
ON CONFLICT (scope_type, scope_id, metric) DO UPDATE
SET numerator = EXCLUDED.numerator, denominator = EXCLUDED.denominator, value = EXCLUDED.value,
    config_version = EXCLUDED.config_version, computed_at = EXCLUDED.computed_at
