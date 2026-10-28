-- Access labels and audit (round 2 W3, docs/round-2-w3-access.md). A document's label lives on registry.document;
-- nodes, pages and table blocks carry their EFFECTIVE label (document combined with any block label), written by
-- the build and copied into the ES indexes by reindex. Labels are JSONB:
-- {classification, domains, owner, embargo_until, label_source[, lowered_reason]}.
ALTER TABLE registry.document ADD COLUMN access JSONB;
ALTER TABLE content.node ADD COLUMN access JSONB;
ALTER TABLE content.page ADD COLUMN access JSONB;
ALTER TABLE content.table_block ADD COLUMN access JSONB;

-- One row per tool call made by a subject: what was returned and how much the policy hid. Audit only; nothing here
-- is ever returned to the caller.
CREATE TABLE quality.access_audit (
    id           BIGSERIAL   PRIMARY KEY,
    trace_id     UUID,
    subject      TEXT        NOT NULL,
    tool         TEXT        NOT NULL,
    returned_ids TEXT[]      NOT NULL DEFAULT '{}',
    n_filtered   INT         NOT NULL DEFAULT 0 CHECK (n_filtered >= 0),
    detail       JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX access_audit_subject_idx ON quality.access_audit (subject, created_at DESC);
CREATE INDEX access_audit_trace_idx ON quality.access_audit (trace_id);
