INSERT INTO fact.fact_version (fact_id, version_no, known_from, known_to, value, status, n_sources, winning_obs_id)
VALUES (%(fact_id)s, %(version_no)s, %(known_from)s, %(known_to)s, %(value)s, %(status)s, %(n_sources)s,
    %(winning_obs_id)s)
