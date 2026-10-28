SELECT concept_id, name_en, name_zh, value_type, default_period_kind, derive
FROM concept.concept WHERE concept_id = %(concept_id)s
