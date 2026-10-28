-- concepts no longer in concepts.yaml (fails while tags, observations or facts still reference them: rebuild first)
DELETE FROM concept.concept WHERE NOT (concept_id = ANY(%(ids)s))
