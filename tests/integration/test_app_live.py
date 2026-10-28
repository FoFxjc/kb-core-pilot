import pytest
from fastapi.testclient import TestClient

from kb_core.build.run import build_doc, run_facts
from kb_core.config import load_settings
from kb_core.es.client import es_client
from kb_core.es.indexer import reindex
from kb_core.intake.importer import import_path
from kb_core.pg.migrate import migrate
from tests.conftest import PG_DSN
from tests.fixtures.mini_package import DOC, build_package

pytestmark = [pytest.mark.pg, pytest.mark.es]


@pytest.fixture
def client(pg_conn, es_settings, tmp_path):
    from kb_core.serve.app import create_app

    migrate(pg_conn)
    s = load_settings({"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": es_settings.es_url, "KB_CORE_INDEX_PREFIX": "kbtest_",
                       "KB_CORE_STORE_DIR": str(tmp_path / "store")}, env_file=None)
    import_path(pg_conn, s, build_package(tmp_path / "delivery"))
    build_doc(pg_conn, s, DOC)
    run_facts(pg_conn)
    reindex(pg_conn, es_client(s), s)
    with TestClient(create_app(s), base_url="http://127.0.0.1:8200") as c:
        yield c


def test_search_route_returns_envelope(client):
    r = client.post("/v1/search", json={"query": "net profit"})
    assert r.status_code == 200
    body = r.json()
    assert body["tool"] == "search" and body["trace_id"].startswith("tr_") and body["results"]


def test_read_route_and_error_shape(client):
    r = client.get("/v1/read", params={"doc_id": DOC, "page_range": "2-3"})
    assert r.status_code == 200 and [p["page_no"] for p in r.json()["results"]] == [2, 3]
    bad = client.get("/v1/read", params={"node_id": "nope:regions:0000"})
    assert bad.status_code == 404 and bad.json()["error"]["code"] == "UNKNOWN_NODE"


def test_page_png_served_from_store(client):
    r = client.get(f"/v1/docs/{DOC}/pages/2.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:4] == b"\x89PNG"


def test_mcp_endpoint_is_mounted(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        headers={"accept": "application/json, text/event-stream"})
    assert r.status_code == 200


def test_tool_routes_return_envelopes(client):
    calls = {"browse": client.get(f"/v1/docs/{DOC}/tree", params={"depth": 1}),
             "resolve_concept": client.post("/v1/resolve_concept", json={"term": "NPL ratio"}),
             "get_metric_series": client.post("/v1/get_metric_series", json={"concept_id": "npl_ratio"})}
    for tool, r in calls.items():
        assert r.status_code == 200, (tool, r.text)
        assert r.json()["tool"] == tool and r.json()["trace_id"].startswith("tr_")


def test_unknown_call_source_is_rejected(client):
    r = client.post("/v1/search", json={"query": "net profit"}, headers={"X-KB-Source": "robot"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_PARAM"


def test_admin_docs_runs_and_nodes(client):
    docs = client.get("/v1/admin/docs").json()["docs"]
    assert [d["doc_id"] for d in docs] == [DOC] and docs[0]["status"] == "built"
    runs = client.get("/v1/admin/runs", params={"doc_id": DOC}).json()["runs"]
    assert {"import", "tree"} <= {r["stage"] for r in runs}
    nodes = client.get(f"/v1/admin/docs/{DOC}/nodes").json()["nodes"]
    assert nodes and {"node_id", "parent_id", "title", "start_page", "end_page", "concepts"} <= set(nodes[0])
    assert client.get("/v1/admin/docs/nope/nodes").status_code == 404


def test_admin_traces_list_one_trace_and_session(client):
    env = client.post("/v1/search", json={"query": "net profit"}, headers={"X-KB-Source": "ui", "X-KB-Session": "s1"}).json()
    listed = client.get("/v1/admin/traces", params={"source": "ui", "limit": 5}).json()["traces"]
    assert listed[0]["trace_id"] == env["trace_id"] and listed[0]["tool"] == "search"
    one = client.get(f"/v1/admin/traces/{env['trace_id']}").json()
    assert one["input"]["query"] == "net profit" and "detail" in one["output"]
    assert client.get("/v1/admin/traces/tr_00000000000000000000000000000000").status_code == 404
    session = client.get("/v1/admin/sessions/s1").json()["calls"]
    assert [c["trace_id"] for c in session] == [env["trace_id"]]


def test_admin_evals_and_page_regions(client):
    assert client.get("/v1/admin/evals", params={"kind": "recall"}).json()["runs"] == []
    regions = client.get(f"/v1/docs/{DOC}/pages/2/regions").json()
    assert regions["width"] > 0 and regions["height"] > 0 and "page_label" in regions
    assert regions["regions"] and {"region_id", "type", "bbox", "node_id"} <= set(regions["regions"][0])
    assert client.get(f"/v1/docs/{DOC}/pages/999/regions").status_code == 404


def test_admin_import_is_idempotent(client, tmp_path):
    r = client.post("/v1/admin/import", json={"path": str(tmp_path / "delivery")})
    assert r.status_code == 200 and [x["created"] for x in r.json()["imported"]] == [False]


def test_mcp_lists_five_tools_over_http(client):
    h = {"accept": "application/json, text/event-stream"}
    init = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}, headers=h)
    sid = init.headers.get("mcp-session-id")
    h2 = {**h, **({"mcp-session-id": sid} if sid else {}), "mcp-protocol-version": "2025-06-18"}
    client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h2)
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=h2)
    assert all(name in r.text for name in ("search", "browse", "read", "resolve_concept", "get_metric_series"))


def test_admin_config_reports_replay_mode(client):
    body = client.get("/v1/admin/config").json()
    assert body == {"contract": "v1", "llm_enabled": False, "live_chat": False, "mode": "replay", "role_picker": True}


def test_admin_replays_list_recorded_sessions(client, monkeypatch, tmp_path):
    import yaml

    from kb_core.serve import admin

    (tmp_path / "mcp_demo_x.yaml").write_text(yaml.safe_dump({
        "run": "demo x", "session_id": "s-demo", "questions": {"d1": "What was the NPL ratio?"}, "answer": "0.9%",
        "tool_calls": [{"tool": "search", "trace_id": "tr_1", "params": {"query": "NPL"}}]}))
    monkeypatch.setattr(admin, "replay_dir", lambda: tmp_path)
    replays = client.get("/v1/admin/replays").json()["replays"]
    assert replays == [{"id": "mcp_demo_x", "run": "demo x", "session_id": "s-demo",
                        "questions": {"d1": "What was the NPL ratio?"}, "answer": "0.9%",
                        "tool_calls": [{"tool": "search", "trace_id": "tr_1", "params": {"query": "NPL"}}]}]


def test_ui_serves_the_built_app_with_deep_links(client, monkeypatch, tmp_path):
    from kb_core.serve import app as app_module

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>kb-core ui</html>")
    (tmp_path / "assets" / "main-abc.js").write_text("console.log(1)")
    monkeypatch.setattr(app_module, "ui_dir", lambda: tmp_path)
    assert "kb-core ui" in client.get("/ui/").text
    assert "kb-core ui" in client.get("/ui/docs/x/pages/3").text           # client-side route
    assert client.get("/ui/assets/main-abc.js").text == "console.log(1)"
    assert client.get("/ui/assets/missing.js").status_code == 404


def test_framework_errors_use_the_contract_envelope(client):
    bad_json = client.post("/v1/search", content=b"notjson", headers={"content-type": "application/json"})
    assert bad_json.status_code == 400 and bad_json.json()["error"]["code"] == "INVALID_PARAM"
    not_object = client.post("/v1/search", json=[1])
    assert not_object.status_code == 400 and not_object.json()["error"]["code"] == "INVALID_PARAM"
    bad_path = client.get(f"/v1/docs/{DOC}/pages/abc/regions")
    assert bad_path.status_code == 400 and bad_path.json()["error"]["code"] == "INVALID_PARAM"
    unknown = client.get("/v1/nope")
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "NOT_FOUND"
    wrong_method = client.get("/v1/search")
    assert wrong_method.status_code == 405 and wrong_method.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert wrong_method.json()["error"]["details"]["allowed"] == ["POST"]
    for cursor in ("99999999999999999999", "²"):
        r = client.get("/v1/admin/traces", params={"cursor": cursor})
        assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_PARAM"
    assert client.get("/ui/%00").status_code == 404


def test_read_accepts_page_range_as_repeated_keys(client):
    r = client.get(f"/v1/read?doc_id={DOC}&page_range=2&page_range=3")
    assert r.status_code == 200 and [p["page_no"] for p in r.json()["results"]] == [2, 3]
