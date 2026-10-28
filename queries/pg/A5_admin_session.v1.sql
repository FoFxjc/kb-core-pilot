-- Admin: the tool calls of one session in time order.
SELECT trace_id, kind, source, started_at, duration_ms, status, error, input, output -> 'gaps' AS gaps,
       output -> 'results' AS results
FROM quality.trace_event
WHERE session_id = %(session_id)s
ORDER BY started_at, id
