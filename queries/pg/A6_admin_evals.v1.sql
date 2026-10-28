-- Admin: evaluation runs newest first with hit counts per variant (crossyear counts questions hit in every year).
SELECT r.run_id, r.kind, r.label, r.started_at, r.finished_at, r.git_sha, r.config, r.question_set,
       (SELECT count(*) FROM eval.eval_result x WHERE x.run_id = r.run_id AND x.variant = 'with_year' AND x.hit) AS with_year_hits,
       (SELECT count(*) FROM eval.eval_result x WHERE x.run_id = r.run_id AND x.variant = 'no_year' AND x.hit) AS no_year_hits,
       (SELECT count(*) FROM (SELECT question_id FROM eval.eval_result x WHERE x.run_id = r.run_id
                              AND x.variant = 'crossyear' GROUP BY question_id HAVING bool_and(x.hit)) q) AS crossyear_hits
FROM eval.eval_run r
WHERE (%(kind)s::text IS NULL OR r.kind = %(kind)s)
ORDER BY r.started_at DESC
LIMIT {limit}
