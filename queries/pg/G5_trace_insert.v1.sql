INSERT INTO quality.trace_event (trace_id, span_id, parent_span_id, kind, source, doc_id, session_id, input, output,
    started_at, duration_ms, status, error)
VALUES (%(trace_id)s, %(span_id)s, NULL, %(kind)s, %(source)s, %(doc_id)s, %(session_id)s, %(input)s, %(output)s,
    %(started_at)s, %(duration_ms)s, %(status)s, %(error)s)
