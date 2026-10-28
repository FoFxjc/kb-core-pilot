-- K2 alias_prefix: prefix match on normalised aliases or concept_ids, shortest hit first; %(prefix)s is escaped.
SELECT concept_id, 'prefix' AS match, min(l) AS shortest
FROM (
    SELECT concept_id, length(alias_norm) AS l FROM concept.concept_alias
    WHERE alias_norm LIKE %(prefix)s ESCAPE '\' AND (%(lang)s = 'any' OR lang = %(lang)s)
    UNION ALL
    SELECT concept_id, length(concept_id) AS l FROM concept.concept WHERE concept_id LIKE lower(%(prefix)s) ESCAPE '\'
) hits
GROUP BY concept_id
ORDER BY shortest, concept_id
LIMIT %(limit)s
