-- Regression snapshot: fact counts (statuses over every fact version, as `kb-core facts` reports them).
SELECT (SELECT count(*) FROM fact.observation) AS observations,
       (SELECT count(*) FROM fact.fact) AS facts,
       count(*) FILTER (WHERE v.status = 'agreed') AS agreed,
       count(*) FILTER (WHERE v.status = 'single') AS single,
       count(*) FILTER (WHERE v.status = 'conflict') AS conflict,
       (SELECT count(*) FROM (SELECT fact_id FROM fact.fact_version GROUP BY fact_id HAVING count(*) > 1) r)
           AS restated,
       (SELECT coalesce(array_agg(DISTINCT f.concept_id ORDER BY f.concept_id), '{}') FROM fact.fact f) AS metrics_covered
FROM fact.fact_version v
