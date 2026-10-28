-- Eval runs and results (design §4.1; kb schemas/postgres/eval.sql).
CREATE SCHEMA IF NOT EXISTS eval;

CREATE TABLE eval.eval_run (
    run_id       TEXT        PRIMARY KEY,
    kind         TEXT        NOT NULL CHECK (kind IN ('recall', 'agent', 'tree', 'concepts')),
    started_at   TIMESTAMPTZ NOT NULL,
    finished_at  TIMESTAMPTZ,
    git_sha      TEXT,
    config       JSONB       NOT NULL,
    question_set JSONB       NOT NULL,          -- [{file, sha256}]
    note         TEXT,
    label        TEXT
);
CREATE INDEX eval_run_started_idx ON eval.eval_run (started_at DESC);

CREATE TABLE eval.eval_result (
    id           BIGSERIAL PRIMARY KEY,
    run_id       TEXT      NOT NULL REFERENCES eval.eval_run (run_id) ON DELETE CASCADE,
    question_id  TEXT      NOT NULL,
    variant      TEXT      NOT NULL CHECK (variant IN ('with_year', 'no_year', 'crossyear', 'agent')),
    year         INTEGER,
    hit          BOOLEAN,
    best_rank    INTEGER,
    hit_node_ids TEXT[],
    trace_id     TEXT,
    detail       JSONB
);
CREATE UNIQUE INDEX eval_result_key_idx ON eval.eval_result (run_id, question_id, variant, COALESCE(year, 0));

CREATE TABLE eval.answer_check (
    run_id      TEXT NOT NULL REFERENCES eval.eval_run (run_id) ON DELETE CASCADE,
    session_key TEXT NOT NULL,
    question_id TEXT NOT NULL,
    check_id    TEXT NOT NULL CHECK (check_id IN ('C1', 'C2', 'C3', 'C4', 'C5')),
    status      TEXT NOT NULL CHECK (status IN ('pass', 'fail', 'review')),
    detail      JSONB,
    PRIMARY KEY (run_id, question_id, check_id)
);
