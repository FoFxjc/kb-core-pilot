-- sections tagged with a concept, strongest first (next steps when a concept has no facts)
SELECT node_id, doc_id, confidence FROM concept.node_concept
WHERE concept_id = %(concept_id)s AND status = 'linked'
ORDER BY confidence DESC, doc_id, node_id
