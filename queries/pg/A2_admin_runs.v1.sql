-- Admin: import, build and fact runs, newest first; doc_id and stage are optional filters.
SELECT run_id, doc_id, stage, status, config_version, started_at, finished_at, counts, detail, error
FROM registry.ingest_run
WHERE (%(doc_id)s::text IS NULL OR doc_id = %(doc_id)s) AND (%(stage)s::text IS NULL OR stage = %(stage)s)
ORDER BY started_at DESC, stage
LIMIT {limit}
