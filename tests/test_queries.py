import json

import pytest

from kb_core import queries
from kb_core.queries import TemplateError, es_query, pg_query


@pytest.fixture
def tdir(tmp_path, monkeypatch):
    (tmp_path / "pg").mkdir()
    (tmp_path / "es").mkdir()
    (tmp_path / "pg" / "M1_node_by_id.v1.sql").write_text("SELECT 1 WHERE {filters} LIMIT {limit}")
    (tmp_path / "pg" / "M1_node_by_id.v2.sql").write_text("SELECT 2 WHERE {filters} LIMIT {limit}")
    (tmp_path / "es" / "S1_node_title_bm25.v1.json").write_text(json.dumps(
        {"size": "{{size}}", "query": {"bool": {"must": {"match": {"title_tok": "{{q}}"}},
                                                "filter": "{{filters}}"}}, "note": "a {{q}} b"}))
    monkeypatch.setattr(queries, "QUERIES", tmp_path)
    queries.clear_cache()
    return tmp_path


def test_pg_picks_highest_version(tdir):
    tid, sql = pg_query("M1_node_by_id", filters={"doc_id": ["d1"]}, limit=5)
    assert tid == "M1_node_by_id.v2"
    assert sql.startswith("SELECT 2") and "LIMIT 5" in sql


def test_pg_filters_render_as_bound_params(tdir):
    _, sql = pg_query("M1_node_by_id", filters={"doc_id": ["d1", "d2"], "fiscal_year": [2025]}, limit=3)
    assert "doc_id = ANY(%(f_doc_id)s)" in sql and "fiscal_year = ANY(%(f_fiscal_year)s)" in sql
    assert "d1" not in sql


def test_pg_rejects_unlisted_filter_column(tdir):
    with pytest.raises(TemplateError, match="title"):
        pg_query("M1_node_by_id", filters={"title; drop table x": ["a"]}, limit=1)


def test_pg_limit_must_be_int(tdir):
    with pytest.raises(TemplateError):
        pg_query("M1_node_by_id", filters={}, limit="5; drop")


def test_es_substitutes_whole_values_only(tdir):
    tid, body = es_query("S1_node_title_bm25", {"size": 50, "q": "npl ratio", "filters": [{"term": {"lang": "en"}}]})
    assert tid == "S1_node_title_bm25.v1"
    assert body["size"] == 50
    assert body["query"]["bool"]["must"]["match"]["title_tok"] == "npl ratio"
    assert body["query"]["bool"]["filter"] == [{"term": {"lang": "en"}}]
    assert body["note"] == "a {{q}} b"


def test_es_missing_param_raises(tdir):
    with pytest.raises(TemplateError, match="size"):
        es_query("S1_node_title_bm25", {"q": "x", "filters": []})


def test_es_unknown_param_raises(tdir):
    with pytest.raises(TemplateError, match="extra"):
        es_query("S1_node_title_bm25", {"q": "x", "filters": [], "size": 1, "extra": 1})


def test_unknown_template_raises(tdir):
    with pytest.raises(TemplateError, match="nope"):
        pg_query("nope", filters={}, limit=1)
