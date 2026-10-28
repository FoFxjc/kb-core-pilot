-- Fact layer (design §4.1; kb schemas/postgres/facts.sql). Observations come from document tables;
-- `kb-core facts` rewrites fact, fact_version and fact_obs_link from all observations.
CREATE SCHEMA IF NOT EXISTS fact;

CREATE TABLE fact.observation (
    obs_id        TEXT    PRIMARY KEY,           -- {table_id}:r{row}:c{col}
    doc_id        TEXT    NOT NULL REFERENCES registry.document (doc_id),
    report_year   INT     NOT NULL,              -- fiscal year of the report that contains the observation
    table_id      TEXT    NOT NULL,
    page_no       INT     NOT NULL,
    page_label    TEXT,
    row_label     TEXT    NOT NULL,
    concept_id    TEXT    NOT NULL REFERENCES concept.concept (concept_id),
    entity_id     TEXT    NOT NULL,
    fiscal_year   INT     NOT NULL,
    period_id     TEXT    NOT NULL,              -- D:YYYY-01-01:YYYY-12-31 or I:YYYY-12-31
    value         NUMERIC NOT NULL,              -- in the base unit
    unit          TEXT    NOT NULL,
    raw_value     TEXT    NOT NULL,
    raw_scale     TEXT    NOT NULL,
    snippet       TEXT,
    restated_note BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX observation_concept_idx ON fact.observation (concept_id, fiscal_year);
CREATE INDEX observation_doc_idx ON fact.observation (doc_id);

CREATE TABLE fact.fact (
    fact_id       TEXT PRIMARY KEY,              -- first 16 hex of sha1(concept_id|entity_id|period_id)
    concept_id    TEXT NOT NULL REFERENCES concept.concept (concept_id),
    entity_id     TEXT NOT NULL,
    fiscal_year   INT  NOT NULL,
    period_id     TEXT NOT NULL,
    unit          TEXT NOT NULL,
    restated_note BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (concept_id, entity_id, period_id)
);

CREATE TABLE fact.fact_version (
    fact_id        TEXT    NOT NULL REFERENCES fact.fact (fact_id) ON DELETE CASCADE,
    version_no     INT     NOT NULL,
    known_from     INT     NOT NULL,
    known_to       INT,
    value          NUMERIC NOT NULL,
    status         TEXT    NOT NULL CHECK (status IN ('agreed', 'single', 'conflict')),
    n_sources      INT     NOT NULL,
    winning_obs_id TEXT    NOT NULL REFERENCES fact.observation (obs_id),
    PRIMARY KEY (fact_id, version_no)
);

CREATE TABLE fact.fact_obs_link (
    fact_id    TEXT NOT NULL,
    version_no INT  NOT NULL,
    obs_id     TEXT NOT NULL REFERENCES fact.observation (obs_id),
    role       TEXT NOT NULL CHECK (role IN ('support', 'conflict')),
    PRIMARY KEY (fact_id, version_no, obs_id),
    FOREIGN KEY (fact_id, version_no) REFERENCES fact.fact_version (fact_id, version_no) ON DELETE CASCADE
);
