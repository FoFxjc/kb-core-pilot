-- Concept tags of nodes, with names (link layer basis).
SELECT nc.node_id, nc.concept_id, c.name_zh, c.name_en, nc.method, nc.variant, nc.confidence
FROM concept.node_concept nc JOIN concept.concept c USING (concept_id)
ORDER BY nc.node_id, nc.concept_id
