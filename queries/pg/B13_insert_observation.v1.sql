INSERT INTO fact.observation (obs_id, doc_id, report_year, table_id, page_no, page_label, row_label, concept_id,
    entity_id, fiscal_year, period_id, value, unit, raw_value, raw_scale, snippet, restated_note)
VALUES (%(obs_id)s, %(doc_id)s, %(report_year)s, %(table_id)s, %(page_no)s, %(page_label)s, %(row_label)s,
    %(concept_id)s, %(entity_id)s, %(fiscal_year)s, %(period_id)s, %(value)s, %(unit)s, %(raw_value)s, %(raw_scale)s,
    %(snippet)s, %(restated_note)s)
