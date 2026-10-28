import pytest

from kb_core.build.run import build_doc, run_facts
from kb_core.config import load_settings
from kb_core.es.client import es_client
from kb_core.es.indexer import reindex
from kb_core.intake.importer import import_path
from kb_core.pg.migrate import migrate
from kb_core.retrieval import context
from kb_core.retrieval.browse import browse
from kb_core.retrieval.concepts import resolve_concept
from kb_core.retrieval.core import ApiError
from kb_core.retrieval.facts import get_metric_series
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
    run_facts(pg_conn)
    reindex(pg_conn, es_client(s), s)
    context.init(s)
    yield s
    context.close()


def test_get_metric_series_values_status_and_provenance(service):
    env = get_metric_series({"concept_id": "net_profit"})
    by = {r["fiscal_year"]: r for r in env["results"]}
    assert set(by) == {2024, 2025}
    r = by[2025]
    assert r["tier"] == "fact" and r["status"] == "single" and r["value"] == 1234000000 and r["display"] == "S$1,234m"
    assert r["source"]["doc_id"] == DOC and r["source"]["page_range"] == [2, 2] and r["source"]["page_label_range"] == ["2", "2"]
    assert r["yoy_abs"] == 1234000000 + 5000000
    assert "single_source" in {g["code"] for g in env["gaps"]}
    assert env["scope"]["available_periods"] == [2024, 2025]


def test_get_metric_series_unknown_concept_names_candidates(service):
    with pytest.raises(ApiError) as e:
        get_metric_series({"concept_id": "net_profit_growthx"})
    assert e.value.code == "INVALID_PARAM" and "candidates" in e.value.details


def test_get_metric_series_no_facts_points_to_sources(service):
    env = get_metric_series({"concept_id": "cet1_ratio"})
    gap = next(g for g in env["gaps"] if g["code"] == "period_unavailable")
    assert env["results"] == [] and gap["next"][-1]["tool"] == "search"


def test_search_fact_layer_comes_first(service):
    env = search({"query": "net profit"})
    assert env["results"][0]["tier"] == "fact" and env["results"][0]["concept_id"] == "net_profit"


def test_resolve_concept_exact_prefix_and_unknown(service):
    exact = resolve_concept({"term": "Net profit"})
    assert exact["results"][0]["concept_id"] == "net_profit" and exact["results"][0]["has_facts"]
    prefix = resolve_concept({"term": "net interest inc"})
    assert prefix["results"][0]["match"] == "prefix"
    unknown = resolve_concept({"term": "zzz qqq"})
    assert unknown["results"] == [] and unknown["gaps"][0]["code"] == "concept_unknown"


def test_browse_root_and_errors(service):
    env = browse({"doc_id": DOC, "depth": 1})
    assert env["results"] and all(r["depth"] == 1 for r in env["results"])
    with pytest.raises(ApiError) as e:
        browse({"doc_id": "nope"})
    assert e.value.code == "UNKNOWN_DOC"


def test_every_tool_returns_the_contract_envelope(service):
    from kb_core.retrieval.read import read

    calls = {"search": (search, {"query": "NPL ratio"}), "browse": (browse, {"doc_id": DOC}),
             "read": (read, {"doc_id": DOC, "page_range": [1, 1]}),
             "resolve_concept": (resolve_concept, {"term": "NPL ratio"}),
             "get_metric_series": (get_metric_series, {"concept_id": "npl_ratio"})}
    for tool, (fn, params) in calls.items():
        env = fn(params)
        assert env["tool"] == tool and env["contract"]
        assert {"results", "scope", "gaps", "truncated", "next", "trace_id"} <= set(env)
        assert isinstance(env["results"], list) and env["trace_id"].startswith("tr_")


def test_every_tools_gaps_carry_severity(service):
    env = get_metric_series({"concept_id": "npl_ratio", "fiscal_years": [2031]})
    assert env["gaps"] and all(g.get("severity") in ("info", "warn") for g in env["gaps"])
    env = browse({"doc_id": DOC})
    assert all("severity" in g for g in env["gaps"])


def test_get_metric_series_rejects_an_unknown_issuer(service):
    with pytest.raises(ApiError) as e:
        get_metric_series({"concept_id": "net_profit", "issuer": "nobody"})
    assert e.value.code == "INVALID_PARAM" and e.value.details["param"] == "issuer" and e.value.details["allowed"]
