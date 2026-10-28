"""Round 2 W3 acceptance on the fixture document, live PG + ES: what a subject may not see never shows up in any
route, count, gap, fact or error (T3.4-T3.6)."""

import pytest
import yaml

from kb_core.build.run import build_doc, run_facts
from kb_core.config import load_settings
from kb_core.es.client import es_client
from kb_core.es.indexer import reindex
from kb_core.intake.importer import import_path
from kb_core.pg.migrate import migrate
from kb_core.retrieval import context
from kb_core.retrieval.browse import browse
from kb_core.retrieval.core import ApiError
from kb_core.retrieval.facts import get_metric_series
from kb_core.retrieval.read import read
from kb_core.retrieval.search import search
from tests.conftest import PG_DSN
from tests.fixtures.mini_package import DOC, build_package

pytestmark = [pytest.mark.pg, pytest.mark.es]

OVERLAY = {"version": 1, "simulated": True,
           "default": {"classification": "public", "domains": [], "owner": "ir"},
           "documents": [], "blocks": [{"doc": DOC, "title": "^Overview$",
                                        "label": {"classification": "confidential", "domains": ["finance"]}}]}


@pytest.fixture
def service(pg_conn, es_settings, tmp_path):
    migrate(pg_conn)
    (tmp_path / "labels.yaml").write_text(yaml.safe_dump(OVERLAY))
    s = load_settings({"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": es_settings.es_url, "KB_CORE_INDEX_PREFIX": "kbtest_",
                       "KB_CORE_STORE_DIR": str(tmp_path / "store"),
                       "KB_CORE_ACCESS_LABELS": str(tmp_path / "labels.yaml")}, env_file=None)
    import_path(pg_conn, s, build_package(tmp_path / "delivery"))
    build_doc(pg_conn, s, DOC)
    run_facts(pg_conn)
    reindex(pg_conn, es_client(s), s)
    context.init(s)
    yield s
    context.close()


def _pages(env):
    return {p for r in env["results"] if r.get("source") for p in range(*[r["source"]["page_range"][0],
                                                                          r["source"]["page_range"][1] + 1])}


def test_search_never_returns_or_counts_the_hidden_section(service):
    full = search({"query": "net profit"}, subject="full_access")
    pub = search({"query": "net profit"}, subject="public")
    assert 2 in _pages(full) and 2 not in _pages(pub)
    assert sum(pub["scope"]["hit_counts"]["fiscal_year"].values()) < sum(full["scope"]["hit_counts"]["fiscal_year"].values())
    assert pub["scope"]["hit_counts_unfiltered"] == pub["scope"]["hit_counts"] or \
        sum(pub["scope"]["hit_counts_unfiltered"]["fiscal_year"].values()) < \
        sum(full["scope"]["hit_counts_unfiltered"]["fiscal_year"].values())
    assert not any(r["tier"] == "fact" for r in pub["results"])


def test_facts_from_hidden_tables_do_not_exist_for_the_subject(service):
    full = get_metric_series({"concept_id": "net_profit"}, subject="full_access")
    pub = get_metric_series({"concept_id": "net_profit"}, subject="public")
    assert full["results"] and full["scope"]["available_periods"] == [2024, 2025]
    assert pub["results"] == [] and pub["scope"]["available_periods"] == []
    assert {g["code"] for g in pub["gaps"]} == {"period_unavailable"}


def test_read_and_browse_of_a_hidden_node_look_like_a_missing_one(service):
    overview = next(r for r in browse({"doc_id": DOC}, subject="full_access")["results"] if r["title"] == "Overview")
    with pytest.raises(ApiError) as hidden:
        read({"node_id": overview["node_id"]}, subject="public")
    with pytest.raises(ApiError) as missing:
        read({"node_id": f"{DOC}:regions:9999"}, subject="public")
    assert hidden.value.code == missing.value.code == "UNKNOWN_NODE"
    assert "Overview" not in [r["title"] for r in browse({"doc_id": DOC}, subject="public")["results"]]
    assert read({"doc_id": DOC, "page_range": [2, 2]}, subject="public")["results"] == []


def test_an_unknown_subject_is_rejected(service):
    with pytest.raises(ApiError) as e:
        search({"query": "net profit"}, subject="root")
    assert e.value.code == "INVALID_PARAM"


def test_every_call_is_audited_without_telling_the_caller(service, pg_conn):
    env = search({"query": "net profit"}, subject="public")
    row = pg_conn.execute("SELECT subject, tool, returned_ids, n_filtered FROM quality.access_audit "
                          "WHERE trace_id = %s", [env["trace_id"].removeprefix("tr_")]).fetchone()
    assert row is not None and row[0] == "public" and row[1] == "search" and row[3] > 0
    assert "n_filtered" not in str(env) and "access_audit" not in str(env)
    full = search({"query": "net profit"}, subject="full_access")
    n = pg_conn.execute("SELECT n_filtered FROM quality.access_audit WHERE trace_id = %s",
                        [full["trace_id"].removeprefix("tr_")]).fetchone()[0]
    assert n == 0


def test_http_page_image_and_regions_respect_the_subject(service):
    from fastapi.testclient import TestClient

    from kb_core.serve.app import create_app

    with TestClient(create_app(service), base_url="http://127.0.0.1:8200") as c:
        pub = {"X-KB-Subject": "public"}
        full = {"X-KB-Subject": "full_access"}
        assert c.get(f"/v1/docs/{DOC}/pages/2/regions", headers=full).status_code == 200
        hidden = c.get(f"/v1/docs/{DOC}/pages/2/regions", headers=pub)
        missing = c.get(f"/v1/docs/{DOC}/pages/999/regions", headers=pub)
        assert hidden.status_code == missing.status_code == 404
        assert hidden.json()["error"]["code"] == missing.json()["error"]["code"]
        assert c.get(f"/v1/docs/{DOC}/pages/2.png", headers=pub).status_code == 404
        r = c.post("/v1/search", json={"query": "net profit"}, headers=pub).json()
        assert all(x["source"]["page_range"] != [2, 2] for x in r["results"] if x.get("source"))
        assert c.post("/v1/search", json={"query": "net profit"}, headers={"X-KB-Subject": "root"}).status_code == 400


@pytest.fixture
def embargoed(pg_conn, es_settings, tmp_path):
    overlay = {"version": 1, "simulated": True, "default": {"classification": "public", "domains": [], "owner": "ir"},
               "documents": [{"match": DOC, "label": {"classification": "internal", "domains": ["finance"],
                                                      "owner": "group-finance",
                                                      "embargo_until": "2026-11-15T00:00:00+08:00"}}],
               "blocks": []}
    migrate(pg_conn)
    (tmp_path / "labels.yaml").write_text(yaml.safe_dump(overlay))
    s = load_settings({"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": es_settings.es_url, "KB_CORE_INDEX_PREFIX": "kbtest_",
                       "KB_CORE_STORE_DIR": str(tmp_path / "store"),
                       "KB_CORE_ACCESS_LABELS": str(tmp_path / "labels.yaml")}, env_file=None)
    import_path(pg_conn, s, build_package(tmp_path / "delivery"))
    build_doc(pg_conn, s, DOC)
    run_facts(pg_conn)
    reindex(pg_conn, es_client(s), s)
    context.init(s)
    yield s
    context.close()


def _at(settings, when: str | None, flag: bool = True):
    """Run with the test clock: KB_CORE_NOW / KB_CORE_ALLOW_CLOCK_OVERRIDE as the running settings."""
    from dataclasses import replace

    from kb_core.config import _time, use

    use(replace(settings, clock_override=flag, now=_time("KB_CORE_NOW", when) if when else None))


def test_the_embargo_flips_at_its_time_with_the_test_clock(embargoed):
    _at(embargoed, "2026-11-14T23:59:00+08:00")
    before = get_metric_series({"concept_id": "net_profit"}, subject="finance_analyst")
    assert before["results"] == [] and search({"query": "net profit"}, subject="finance_analyst")["results"] == []
    assert get_metric_series({"concept_id": "net_profit"}, subject="finance_confidential")["results"]   # exempt
    _at(embargoed, "2026-11-15T00:00:00+08:00")
    after = get_metric_series({"concept_id": "net_profit"}, subject="finance_analyst")
    assert after["results"] and after["results"][-1]["value"] == 1234000000
    assert search({"query": "net profit"}, subject="public")["results"] == []          # still internal to finance


def test_the_test_clock_is_ignored_without_its_flag(embargoed):
    from datetime import UTC, datetime, timedelta

    from kb_core.access.policy import now

    _at(embargoed, "2030-01-01T00:00:00+00:00", flag=False)
    assert abs(now() - datetime.now(UTC)) < timedelta(minutes=5)      # real time, whatever KB_CORE_NOW says


def test_a_page_image_can_name_its_subject_in_the_query_for_img_tags(service):
    from fastapi.testclient import TestClient

    from kb_core.serve.app import create_app

    with TestClient(create_app(service), base_url="http://127.0.0.1:8200") as c:
        assert c.get(f"/v1/docs/{DOC}/pages/2.png?subject=full_access").status_code == 200
        assert c.get(f"/v1/docs/{DOC}/pages/2.png?subject=public").status_code == 404
        assert c.get(f"/v1/docs/{DOC}/pages/2.png?subject=root").status_code == 400


def test_search_outlines_and_concept_counts_never_mention_hidden_sections(service):
    from kb_core.retrieval.concepts import resolve_concept

    env = search({"query": "financial statements"}, subject="public")
    assert not any("Overview" in line for r in env["results"] for line in r.get("local_outline") or [])
    full = resolve_concept({"term": "net profit"}, subject="full_access")["results"][0]["node_count"]
    pub = resolve_concept({"term": "net profit"}, subject="public")["results"][0]["node_count"]
    assert pub < full


def test_admin_document_nodes_respect_the_subject(service):
    from fastapi.testclient import TestClient

    from kb_core.serve.app import create_app

    with TestClient(create_app(service), base_url="http://127.0.0.1:8200") as c:
        titles = [n["title"] for n in c.get(f"/v1/admin/docs/{DOC}/nodes", headers={"X-KB-Subject": "public"}).json()["nodes"]]
        assert "Overview" not in titles
        assert "Overview" in [n["title"] for n in c.get(f"/v1/admin/docs/{DOC}/nodes",
                                                         headers={"X-KB-Subject": "full_access"}).json()["nodes"]]


def test_search_rechecks_results_against_the_stored_labels(service, pg_conn):
    before = search({"query": "financial statements"}, subject="public")
    assert [r for r in before["results"] if r["tier"] != "fact"]                # visible before the label change
    # make the stored label stricter than the index (an overlay change and rebuild without a reindex)
    pg_conn.execute("UPDATE content.node SET access = jsonb_set(access, '{classification}', '\"restricted\"') "
                    "WHERE doc_id = %s", [DOC])
    pg_conn.execute("UPDATE content.page SET access = jsonb_set(access, '{classification}', '\"restricted\"') "
                    "WHERE doc_id = %s", [DOC])
    context.current().catalog.refresh()
    env = search({"query": "financial statements"}, subject="public")
    assert [r for r in env["results"] if r["tier"] != "fact"] == []


# --- behind the SSO gateway (enterprise readiness B) --------------------------------------------------------------------

def _gateway(settings, tmp_path):
    from dataclasses import replace

    (tmp_path / "role_map.yaml").write_text("groups: {staff: public, fin-conf: finance_confidential}\n"
                                            "admin_groups: [kb-admins]\n")
    return replace(settings, env="production", auth_mode="trusted_header", auth_user_header="X-Auth-User",
                   auth_groups_header="X-Auth-Groups", access_role_map=tmp_path / "role_map.yaml")


def test_gateway_users_get_their_role_and_are_audited_by_name(service, pg_conn, tmp_path):
    from fastapi.testclient import TestClient

    from kb_core.serve.app import create_app

    with TestClient(create_app(_gateway(service, tmp_path)), base_url="http://127.0.0.1:8200") as c:
        staff = {"X-Auth-User": "alice@example.com", "X-Auth-Groups": "staff"}
        conf = {"X-Auth-User": "bob@example.com", "X-Auth-Groups": "staff,fin-conf"}
        r_pub = c.post("/v1/search", json={"query": "net profit"}, headers=staff)
        r_conf = c.post("/v1/search", json={"query": "net profit"}, headers=conf)
        assert r_pub.status_code == r_conf.status_code == 200
        pages = lambda r: {x["source"]["page_range"][0] for x in r.json()["results"] if x.get("source")}  # noqa: E731
        assert 2 not in pages(r_pub) and 2 in pages(r_conf)                 # the confidential section
        assert c.get(f"/v1/docs/{DOC}/pages/2.png", headers=staff).status_code == 404
        assert c.get(f"/v1/docs/{DOC}/pages/2.png", headers=conf).status_code == 200
        assert c.post("/v1/search", json={"query": "net profit"}).status_code == 401
        assert c.get("/v1/admin/config", headers=conf).status_code == 403
        admin = c.get("/v1/admin/config", headers={"X-Auth-User": "ops", "X-Auth-Groups": "kb-admins"})
        assert admin.status_code == 200 and admin.json()["role_picker"] is False
    rows = pg_conn.execute("SELECT user_id, subject FROM quality.access_audit WHERE trace_id = ANY(%s)",
                           ([r_pub.json()["trace_id"].removeprefix("tr_"),
                             r_conf.json()["trace_id"].removeprefix("tr_")],)).fetchall()
    assert sorted(rows) == [("alice@example.com", "public"), ("bob@example.com", "finance_confidential")]


def test_mcp_behind_the_gateway_uses_the_same_identity(service, tmp_path):
    from fastapi.testclient import TestClient

    from kb_core.serve.app import create_app

    h = {"accept": "application/json, text/event-stream"}
    with TestClient(create_app(_gateway(service, tmp_path)), base_url="http://127.0.0.1:8200") as c:
        assert c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}, headers=h).status_code == 401
        for groups, sees in (("staff", False), ("fin-conf", True)):
            who = {**h, "X-Auth-User": "u@example.com", "X-Auth-Groups": groups}
            init = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
                headers=who)
            sid = init.headers.get("mcp-session-id")
            h2 = {**who, **({"mcp-session-id": sid} if sid else {}), "mcp-protocol-version": "2025-06-18"}
            c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h2)
            r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "read", "arguments": {"doc_id": DOC, "page_range": [2, 2]}}}, headers=h2)
            assert ('"page_no":2' in r.text.replace(" ", "")) is sees, r.text[:300]
