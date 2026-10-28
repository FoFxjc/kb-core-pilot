-- One evaluation run (eval.eval_run).
INSERT INTO eval.eval_run (run_id, kind, started_at, finished_at, git_sha, config, question_set, note, label)
VALUES (%(run_id)s, %(kind)s, %(started_at)s, %(finished_at)s, %(git_sha)s, %(config)s, %(question_set)s, %(note)s,
        %(label)s)
