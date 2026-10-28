-- Live chat: the latest agent.answer of a session (its output holds the history and the tool calls used).
SELECT output
FROM quality.trace_event
WHERE session_id = %(session_id)s AND kind = 'agent.answer'
ORDER BY started_at DESC, id DESC
LIMIT 1
