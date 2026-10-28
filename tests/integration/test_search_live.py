import pytest

from kb_core.build.run import build_doc
from kb_core.config import load_settings
from kb_core.es.client import es_client
from kb_core.es.indexer import reindex
from kb_core.intake.importer import import_path
from kb_core.pg.migrate import migrate
from kb_core.retrieval import context
from kb_core.retrieval.core import ApiError
from kb_core.retrieval.read import read
from kb_core.retrieval.search import search
from tests.conftest import PG_DSN
from tests.fixtures.mini_package import DOC, build_package

pytestmark = [pytest.mark.pg, pytest.mark.es]


@pytest.fixture
def service(pg_conn, es_settings, tmp_path):
    migrate(pg_conn)
    s = load_settings({"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": es_settings.es_url, "KB_CORE_INDEX_PREFIX": "kbtest_",
                       "KB_CORE_STORE_DIR": str(tmp_path / "store")}, env_file=None)
    import_path(pg_conn, s, build_package(tmp_path / "delivery"))
    build_doc(pg_conn, s, DOC)
    reindex(pg_conn, es_client(s), s)
    context.init(s)
    yield s
    context.close()


def test_search_finds_the_node_and_traces_final_dsl(service, pg_conn):
    env = search({"query": "net profit", "doc_type": "annual_report"})
    assert env["results"], env["gaps"]
    top = env["results"][0]
    assert top["source"]["doc_id"] == DOC and top["source"]["page_range"][0] <= 2 <= top["source"]["page_range"][1]
    assert top["tier"] == "link" and top["matched"]["concepts"][0]["concept_id"] == "net_profit"   # tagged node
    row = pg_conn.execute("SELECT kind, output FROM quality.trace_event WHERE trace_id = %s",
                          [env["trace_id"].removeprefix("tr_")]).fetchone()
    assert row[0] == "tool.search"
    queries = row[1]["detail"]["queries"]
    assert any(k.startswith("S3_page_text_bm25.v") for k in queries)
    assert "net" in str(queries)


def test_filters_rendered_into_dsl(service, pg_conn):
    env = search({"query": "net profit", "fiscal_years": [2025], "lang": "en"})
    dsl = pg_conn.execute("SELECT output -> 'detail' -> 'queries' FROM quality.trace_event WHERE trace_id = %s",
                          [env["trace_id"].removeprefix("tr_")]).fetchone()[0]
    title = next(v for k, v in dsl.items() if k.startswith("S1_node_title_bm25"))
    assert {"terms": {"doc_id": [DOC]}} in title["query"]["bool"]["filter"]


def test_search_low_info_query_returns_gap(service, pg_conn):
    env = search({"query": "OCBC 2025"})
    assert not any(r["tier"] == "structure" for r in env["results"])   # no informative token, no structure layer
    detail = pg_conn.execute("SELECT output -> 'detail' FROM quality.trace_event WHERE trace_id = %s",
                             [env["trace_id"].removeprefix("tr_")]).fetchone()[0]
    assert detail["informative_terms"] == [] and detail["coverage_units"] == []
    assert "concept_unknown" in {g["code"] for g in env["gaps"]}


def test_search_empty_scope_gap(service):
    env = search({"query": "net profit", "fiscal_years": [2019]})
    assert env["results"] == [] and any(g["code"] == "empty_scope" for g in env["gaps"])


def test_read_by_page_range_returns_text_and_tables(service):
    env = read({"doc_id": DOC, "page_range": [2, 3]})
    assert [r["page_no"] for r in env["results"]] == [2, 3]
    assert env["results"][0]["tables"][0]["table_id"].endswith("t0002_01")
    assert env["scope"]["source"]["page_range"] == [2, 3]


def test_read_rejects_node_id_and_page_range(service):
    with pytest.raises(ApiError) as e:
        read({"node_id": f"{DOC}:regions:0000", "doc_id": DOC, "page_range": [1, 1]})
    assert e.value.code == "INVALID_PARAM"


def test_read_unknown_node(service):
    with pytest.raises(ApiError) as e:
        read({"node_id": f"{DOC}:regions:9999"})
    assert e.value.code == "UNKNOWN_NODE"


def test_traces_are_compact_and_never_hold_images(service, pg_conn):
    env = read({"doc_id": DOC, "page_range": [2, 3], "include_images": True})
    assert env["results"][0]["image"]["data_base64"]
    out = pg_conn.execute("SELECT output::text FROM quality.trace_event WHERE trace_id = %s",
                          [env["trace_id"].removeprefix("tr_")]).fetchone()[0]
    assert "data_base64" not in out and "Net profit rose" not in out and len(out) < 5000
    s = search({"query": "net profit"})
    row = pg_conn.execute("SELECT output -> 'results' FROM quality.trace_event WHERE trace_id = %s",
                          [s["trace_id"].removeprefix("tr_")]).fetchone()[0]
    assert set(row[0]) <= {"rank", "tier", "node_id", "doc_id", "page_range", "score", "concept_id", "fiscal_year"}
