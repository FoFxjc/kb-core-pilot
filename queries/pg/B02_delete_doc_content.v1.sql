-- A rebuild deletes every interpretation row of one document before inserting it again.
WITH r AS (DELETE FROM content.region WHERE doc_id = %(doc_id)s),
     t AS (DELETE FROM content.table_block WHERE doc_id = %(doc_id)s),
     m AS (DELETE FROM content.table_merge WHERE doc_id = %(doc_id)s),
     p AS (DELETE FROM content.page WHERE doc_id = %(doc_id)s),
     c AS (DELETE FROM concept.node_concept WHERE doc_id = %(doc_id)s),
     g AS (DELETE FROM quality.gap_log WHERE doc_id = %(doc_id)s AND layer = 'build')
DELETE FROM content.node WHERE doc_id = %(doc_id)s
