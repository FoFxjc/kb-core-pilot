-- Registry: sources (issuers), documents and ingest runs (design §4.1; kb schemas/postgres/sources.sql).
-- A document is one imported delivery package; doc_id comes from the package declaration.
CREATE SCHEMA IF NOT EXISTS registry;

CREATE TABLE registry.source (
    issuer_id   TEXT PRIMARY KEY,
    publisher   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE registry.document (
    doc_id            TEXT PRIMARY KEY,
    issuer_id         TEXT        NOT NULL REFERENCES registry.source (issuer_id),
    doc_type          TEXT        NOT NULL,
    period_end        DATE        NOT NULL,
    fiscal_year       INT         NOT NULL,
    lang              TEXT,
    source_url        TEXT,
    completeness      JSONB,
    translation_of    TEXT,
    publisher         TEXT,
    published_at      DATE,
    page_count        INT         NOT NULL,
    has_text_layer    BOOLEAN,
    package           TEXT        NOT NULL,           -- {doc_id}@{sha256[:12]}
    package_sha256    TEXT        NOT NULL,           -- sha256 of source.pdf
    contract_version  TEXT        NOT NULL,
    status            TEXT        NOT NULL DEFAULT 'imported'
                      CHECK (status IN ('imported', 'built', 'error')),
    manifest          JSONB       NOT NULL,
    imported_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE registry.ingest_run (
    run_id          UUID        NOT NULL,
    doc_id          TEXT,                              -- null for cross-document stages (facts)
    stage           TEXT        NOT NULL,              -- import / tree / sections / chunks / tables / concepts / observations / facts
    status          TEXT        NOT NULL CHECK (status IN ('ok', 'error', 'skipped')),
    config_version  TEXT,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ NOT NULL,
    counts          JSONB,
    detail          JSONB,
    error           TEXT,
    PRIMARY KEY (run_id, stage)
);
CREATE INDEX ingest_run_doc_idx ON registry.ingest_run (doc_id, started_at DESC);
