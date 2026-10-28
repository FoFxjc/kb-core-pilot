-- A rebuild deletes every interpretation row of one document before inserting it again. Facts are derived across
-- documents and reference observations, so they are cleared too (run kb-core facts afterwards).
WITH r AS (DELETE FROM content.region WHERE doc_id = %(doc_id)s),
     t AS (DELETE FROM content.table_block WHERE doc_id = %(doc_id)s),
     m AS (DELETE FROM content.table_merge WHERE doc_id = %(doc_id)s),
     p AS (DELETE FROM content.page WHERE doc_id = %(doc_id)s),
     c AS (DELETE FROM concept.node_concept WHERE doc_id = %(doc_id)s),
     g AS (DELETE FROM quality.gap_log WHERE doc_id = %(doc_id)s AND layer = 'build'),
     fl AS (DELETE FROM fact.fact_obs_link),
     fv AS (DELETE FROM fact.fact_version),
     f AS (DELETE FROM fact.fact),
     o AS (DELETE FROM fact.observation WHERE doc_id = %(doc_id)s)
DELETE FROM content.node WHERE doc_id = %(doc_id)s
