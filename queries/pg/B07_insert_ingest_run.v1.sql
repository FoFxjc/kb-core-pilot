INSERT INTO registry.ingest_run (run_id, doc_id, stage, status, config_version, started_at, finished_at, counts,
    detail, error)
VALUES (%(run_id)s, %(doc_id)s, %(stage)s, %(status)s, %(config_version)s, %(started_at)s, %(finished_at)s,
    %(counts)s, %(detail)s, %(error)s)
