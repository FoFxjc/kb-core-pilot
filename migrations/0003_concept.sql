-- Concept layer (design §4.1; kb schemas/postgres/concepts.sql). Authoritative source: domains/<domain>/concepts.yaml.
CREATE SCHEMA IF NOT EXISTS concept;

CREATE TABLE concept.concept (
    concept_id          TEXT PRIMARY KEY,
    name_en             TEXT NOT NULL,
    name_zh             TEXT NOT NULL,
    value_type          TEXT NOT NULL CHECK (value_type IN ('amount', 'percent', 'ratio', 'bps', 'count')),
    aggregation         TEXT NOT NULL CHECK (aggregation IN ('flow', 'stock', 'ratio')),
    default_period_kind TEXT NOT NULL CHECK (default_period_kind IN ('duration', 'instant')),
    definition          TEXT,
    derive              JSONB,
    spec_version        INT  NOT NULL
);

CREATE TABLE concept.concept_alias (
    alias_norm TEXT PRIMARY KEY,
    alias      TEXT NOT NULL,
    lang       TEXT NOT NULL CHECK (lang IN ('en', 'zh')),
    concept_id TEXT NOT NULL REFERENCES concept.concept (concept_id),
    source     TEXT NOT NULL CHECK (source IN ('manual', 'zh_en_alignment', 'row_label')),
    kind       TEXT NOT NULL CHECK (kind IN ('variants', 'query_only', 'row_labels'))
);
CREATE INDEX concept_alias_concept_idx ON concept.concept_alias (concept_id);

CREATE TABLE concept.concept_edge (
    src_concept_id TEXT NOT NULL REFERENCES concept.concept (concept_id),
    relation       TEXT NOT NULL CHECK (relation IN ('broader', 'component_of', 'variant_of')),
    dst_concept_id TEXT NOT NULL REFERENCES concept.concept (concept_id),
    PRIMARY KEY (src_concept_id, relation, dst_concept_id)
);

CREATE TABLE concept.node_concept (
    node_id    TEXT NOT NULL,
    concept_id TEXT NOT NULL REFERENCES concept.concept (concept_id),
    doc_id     TEXT NOT NULL REFERENCES registry.document (doc_id),
    method     TEXT NOT NULL CHECK (method IN ('rule_title', 'rule_row_label', 'rule_dict', 'manual')),
    variant    TEXT,
    confidence REAL NOT NULL,
    status     TEXT NOT NULL DEFAULT 'linked',
    PRIMARY KEY (node_id, concept_id)
);
CREATE INDEX node_concept_concept_idx ON concept.node_concept (concept_id);
CREATE INDEX node_concept_doc_idx ON concept.node_concept (doc_id);
