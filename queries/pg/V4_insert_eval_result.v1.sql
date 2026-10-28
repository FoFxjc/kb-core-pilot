-- One per-question result of an evaluation run (eval.eval_result).
INSERT INTO eval.eval_result (run_id, question_id, variant, year, hit, best_rank, hit_node_ids, trace_id, detail)
VALUES (%(run_id)s, %(question_id)s, %(variant)s, %(year)s, %(hit)s, %(best_rank)s, %(hit_node_ids)s, %(trace_id)s,
        %(detail)s)
