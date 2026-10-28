-- Regression snapshot: each document's recorded tree spot-check accuracy (kb-core eval tree --record).
SELECT c.scope_id AS doc_id, c.value
FROM quality.coverage c
WHERE c.scope_type = 'document' AND c.metric = 'tree_sample_accuracy'
ORDER BY c.scope_id
