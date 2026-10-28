-- K1 alias_exact (api-contract §5.4): exact concept_id match, or exact normalised alias (lang en / zh restricts).
SELECT concept_id, 'exact' AS match FROM concept.concept WHERE concept_id = lower(%(term)s)
UNION ALL
SELECT DISTINCT concept_id, 'alias' AS match FROM concept.concept_alias
WHERE alias_norm = %(norm)s AND (%(lang)s = 'any' OR lang = %(lang)s)
