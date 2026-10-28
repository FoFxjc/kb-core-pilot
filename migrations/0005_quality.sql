-- Quality: traces, gaps and coverage (design §4.1; kb schemas/postgres/quality.sql, trace_event.sql).
CREATE SCHEMA IF NOT EXISTS quality;

CREATE TABLE quality.trace_event (
    id             BIGSERIAL   PRIMARY KEY,
    trace_id       UUID        NOT NULL,
    span_id        UUID        NOT NULL UNIQUE,
    parent_span_id UUID,
    kind           TEXT        NOT NULL,        -- tool.search / tool.read / ... / ingest.<stage>
    source         TEXT        CHECK (source IN ('mcp', 'chat', 'eval', 'ui', 'http')),
    doc_id         TEXT,
    session_id     TEXT,
    input          JSONB,
    output         JSONB,
    started_at     TIMESTAMPTZ NOT NULL,
    duration_ms    INTEGER     NOT NULL CHECK (duration_ms >= 0),
    status         TEXT        NOT NULL CHECK (status IN ('ok', 'error')),
    error          TEXT
);
CREATE INDEX trace_event_trace_idx ON quality.trace_event (trace_id, started_at);
CREATE INDEX trace_event_kind_idx ON quality.trace_event (kind, started_at DESC);
CREATE INDEX trace_event_session_idx ON quality.trace_event (session_id, started_at);
CREATE INDEX trace_event_started_idx ON quality.trace_event (started_at DESC, id DESC);

-- Gaps: inherited from the intake package (layer 'intake'), found while interpreting (layer 'build'),
-- or returned by a tool call (layer 'tool', with trace_id).
CREATE TABLE quality.gap_log (
    id         BIGSERIAL   PRIMARY KEY,
    layer      TEXT        NOT NULL CHECK (layer IN ('intake', 'build', 'tool')),
    doc_id     TEXT,
    trace_id   UUID,
    code       TEXT        NOT NULL,
    page_no    INT,
    detail     JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX gap_log_code_idx ON quality.gap_log (code, created_at DESC);
CREATE INDEX gap_log_doc_idx ON quality.gap_log (doc_id, layer);

CREATE TABLE quality.coverage (
    scope_type     TEXT        NOT NULL,
    scope_id       TEXT        NOT NULL,
    metric         TEXT        NOT NULL,
    numerator      NUMERIC,
    denominator    NUMERIC,
    value          JSONB       NOT NULL,
    config_version TEXT,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope_type, scope_id, metric)
);
