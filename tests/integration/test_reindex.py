import pytest

from kb_core.build.run import build_doc
from kb_core.config import load_settings
from kb_core.es.client import es_client
from kb_core.es.indexes import alias_name, alias_targets
from kb_core.es.indexer import reindex
from kb_core.intake.importer import import_path
from kb_core.pg.migrate import migrate
from tests.conftest import PG_DSN
from tests.fixtures.mini_package import DOC, build_package

pytestmark = [pytest.mark.pg, pytest.mark.es]
OTHER = "acme_ar_2024_en"


@pytest.fixture
def built(pg_conn, es_settings, tmp_path):
    migrate(pg_conn)
    s = load_settings({"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": es_settings.es_url,
                       "KB_CORE_INDEX_PREFIX": "kbtest_", "KB_CORE_STORE_DIR": str(tmp_path / "store")}, env_file=None)
    build_package(tmp_path / "delivery")
    build_package(tmp_path / "delivery", doc_id=OTHER, period_end="2024-12-31", cover="Acme Annual Report 2024")
    import_path(pg_conn, s, tmp_path / "delivery")
    for d in (DOC, OTHER):
        build_doc(pg_conn, s, d)
    return pg_conn, es_client(s), s


def es_count(es, s, kind, doc_id=None):
    q = {"query": {"term": {"doc_id": doc_id}}} if doc_id else {"query": {"match_all": {}}}
    return es.request("POST", f"/{alias_name(s, kind)}/_count", json=q)["count"]


def pg_count(conn, table, doc_id=None):
    if doc_id:
        return conn.execute(f"SELECT count(*) FROM {table} WHERE doc_id = %s", [doc_id]).fetchone()[0]
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_reindex_counts_match_pg(built):
    conn, es, s = built
    summary = reindex(conn, es, s)
    assert summary.nodes == pg_count(conn, "content.node") and summary.pages == pg_count(conn, "content.page")
    assert es_count(es, s, "node") == summary.nodes and es_count(es, s, "page") == summary.pages
    hit = es.request("POST", f"/{alias_name(s, 'page')}/_search",
                     json={"query": {"match": {"text_tok": "overview"}}})["hits"]["hits"]
    assert {h["_source"]["doc_id"] for h in hit} == {DOC, OTHER}


def test_reindex_doc_replaces_only_that_doc(built):
    conn, es, s = built
    reindex(conn, es, s)
    conn.execute("UPDATE content.node SET title_tok = 'renamedtoken' WHERE doc_id = %s", [DOC])
    conn.execute("UPDATE content.node SET title_tok = 'untouchedtoken' WHERE doc_id = %s", [OTHER])
    before = alias_targets(es, alias_name(s, "node"))
    reindex(conn, es, s, doc_id=DOC)
    assert alias_targets(es, alias_name(s, "node")) == before            # same physical index
    search = lambda tok: es.request("POST", f"/{alias_name(s, 'node')}/_search",  # noqa: E731
                                    json={"query": {"match": {"title_tok": tok}}})["hits"]["total"]["value"]
    assert search("renamedtoken") == pg_count(conn, "content.node", DOC)
    assert search("untouchedtoken") == 0
    assert es_count(es, s, "node", OTHER) == pg_count(conn, "content.node", OTHER)


def test_reindex_after_index_deleted(built):
    conn, es, s = built
    reindex(conn, es, s)
    for kind in ("node", "page"):
        for idx in alias_targets(es, alias_name(s, kind)):
            es.request("DELETE", f"/{idx}")
    summary = reindex(conn, es, s)
    assert es_count(es, s, "node") == summary.nodes == pg_count(conn, "content.node")
    assert es_count(es, s, "page") == summary.pages


def test_reindex_doc_without_aliases_does_a_full_rebuild(built):
    conn, es, s = built
    summary = reindex(conn, es, s, doc_id=DOC)
    assert summary.full and es_count(es, s, "node") == pg_count(conn, "content.node")


def test_cli_reindex(built, monkeypatch, capsys, tmp_path):
    import json

    from kb_core.cli import main

    conn, es, s = built
    monkeypatch.chdir(tmp_path)
    for k, v in {"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": s.es_url, "KB_CORE_INDEX_PREFIX": "kbtest_"}.items():
        monkeypatch.setenv(k, v)
    assert main(["reindex"]) == 0
    out = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert out["full"] and out["nodes"] == pg_count(conn, "content.node")
