-- One access audit row per tool call (round 2 W3, T3.7): who asked, what was returned, how much the policy hid.
-- Audit only: never part of a tool response.
INSERT INTO quality.access_audit (trace_id, subject, tool, returned_ids, n_filtered, detail)
VALUES (%(trace_id)s, %(subject)s, %(tool)s, %(returned_ids)s, %(n_filtered)s, %(detail)s)
