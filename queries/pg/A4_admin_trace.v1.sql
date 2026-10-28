-- Admin: the events of one trace.
SELECT id, trace_id, kind, source, session_id, started_at, duration_ms, status, error, input, output
FROM quality.trace_event
WHERE trace_id = %(trace_id)s
ORDER BY started_at, id
