-- Admin: tool trace events newest first; optional filters; cursor = the id of the last row of the previous page.
SELECT id, trace_id, kind, source, session_id, started_at, duration_ms, status, error, input,
       output -> 'gaps' AS gaps, jsonb_array_length(coalesce(output -> 'results', '[]'::jsonb)) AS n_results
FROM quality.trace_event
WHERE kind LIKE 'tool.%%'
  AND (%(source)s::text IS NULL OR source = %(source)s)
  AND (%(tool)s::text IS NULL OR kind = 'tool.' || %(tool)s)
  AND (%(session_id)s::text IS NULL OR session_id = %(session_id)s)
  AND (%(from)s::timestamptz IS NULL OR started_at >= %(from)s)
  AND (%(to)s::timestamptz IS NULL OR started_at < %(to)s)
  AND (%(cursor)s::bigint IS NULL OR id < %(cursor)s)
ORDER BY id DESC
LIMIT {limit}
