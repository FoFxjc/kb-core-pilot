-- Content: tree nodes, pages, intake regions, tables and continued-table merges (design §4.1; kb Doris
-- schemas/doris/01_tables.sql turned into Postgres tables; region and table_merge are new).
-- Every row carries doc_id; a rebuild deletes a document's rows and inserts them again.
CREATE SCHEMA IF NOT EXISTS content;

CREATE TABLE content.node (
    doc_id           TEXT    NOT NULL REFERENCES registry.document (doc_id),
    node_id          TEXT    PRIMARY KEY,
    parent_id        TEXT,
    ancestors        TEXT[]  NOT NULL DEFAULT '{}',
    depth            INT     NOT NULL,
    ord              INT     NOT NULL,
    title            TEXT    NOT NULL,
    title_tok        TEXT,
    summary          TEXT,
    summary_tok      TEXT,
    start_page       INT     NOT NULL,
    end_page         INT     NOT NULL,
    page_label_range TEXT[],
    tree_source      TEXT    NOT NULL,
    origin           TEXT    NOT NULL,
    is_primary       BOOLEAN NOT NULL,
    section_type     TEXT,
    section_rule     TEXT,
    fiscal_year      INT     NOT NULL,
    lang             TEXT,
    issuer           TEXT    NOT NULL,
    concept_ids      TEXT[]  NOT NULL DEFAULT '{}',
    concept_tok      TEXT,
    region_ids       TEXT[]  NOT NULL DEFAULT '{}',
    ext              JSONB
);
CREATE INDEX node_doc_idx ON content.node (doc_id, ord);

CREATE TABLE content.page (
    doc_id            TEXT    NOT NULL REFERENCES registry.document (doc_id),
    page_no           INT     NOT NULL,
    page_label        TEXT,
    page_label_source TEXT,
    kind              TEXT,
    excluded          BOOLEAN NOT NULL DEFAULT false,
    width             REAL,
    height            REAL,
    fiscal_year       INT     NOT NULL,
    lang              TEXT,
    issuer            TEXT    NOT NULL,
    text              TEXT,
    text_tok          TEXT,
    covering_node_ids TEXT[]  NOT NULL DEFAULT '{}',
    PRIMARY KEY (doc_id, page_no)
);

CREATE TABLE content.region (
    doc_id         TEXT    NOT NULL REFERENCES registry.document (doc_id),
    region_id      TEXT    PRIMARY KEY,
    page_no        INT     NOT NULL,
    bbox           REAL[]  NOT NULL,
    type           TEXT    NOT NULL,
    subtype        TEXT,
    layer          TEXT    NOT NULL,
    reading_order  INT     NOT NULL,
    text           TEXT,
    font           JSONB,
    status         TEXT    NOT NULL,
    table_id       TEXT,
    node_id        TEXT
);
CREATE INDEX region_doc_page_idx ON content.region (doc_id, page_no, reading_order);

CREATE TABLE content.table_block (
    doc_id         TEXT    NOT NULL REFERENCES registry.document (doc_id),
    table_id       TEXT    PRIMARY KEY,
    region_id      TEXT,
    node_id        TEXT,
    page_start     INT     NOT NULL,
    page_end       INT     NOT NULL,
    bbox           REAL[],
    n_rows         INT     NOT NULL,
    n_cols         INT     NOT NULL,
    caption        TEXT,
    unit_hint      TEXT,
    markdown       TEXT,
    extract_method TEXT,
    table_kind     TEXT,
    cells          JSONB   NOT NULL,            -- intake cells, as delivered
    parsed         JSONB,                       -- interpreted header rows, row paths and values
    continued_hint JSONB
);
CREATE INDEX table_block_doc_idx ON content.table_block (doc_id, page_start);

CREATE TABLE content.table_merge (
    merge_id        TEXT    PRIMARY KEY,         -- first part's table_id
    doc_id          TEXT    NOT NULL REFERENCES registry.document (doc_id),
    part_table_ids  TEXT[]  NOT NULL,
    reason          TEXT    NOT NULL,            -- continued_hint.reason
    decision        TEXT    NOT NULL CHECK (decision IN ('merged', 'hint')),
    header_from     TEXT
);
