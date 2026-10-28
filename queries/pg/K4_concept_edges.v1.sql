SELECT src_concept_id, relation, dst_concept_id FROM concept.concept_edge
WHERE src_concept_id = ANY(%(ids)s) OR dst_concept_id = ANY(%(ids)s)
ORDER BY src_concept_id, relation, dst_concept_id
