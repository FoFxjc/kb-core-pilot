import pytest

from kb_core import cli, doctor
from kb_core.config import load_settings
from kb_core.doctor import Check

BASE = {"KB_CORE_PG_DSN": "postgresql://unused", "KB_CORE_ES_URL": "http://unused"}


def test_default_bind_is_localhost():
    from kb_core.serve.app import uvicorn_options

    opts = uvicorn_options(load_settings(BASE, env_file=None))
    assert opts["host"] == "127.0.0.1" and opts["port"] == 8200


def test_serve_refuses_when_doctor_fails(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    for k, v in BASE.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(doctor, "run_checks", lambda s: [Check("pg_connect", "fail", "refused", "check KB_CORE_PG_DSN")])
    started = []
    monkeypatch.setattr("kb_core.serve.app.run", lambda s: started.append(s))
    assert cli.main(["serve"]) == 1
    assert started == [] and "pg_connect" in capsys.readouterr().err


def test_serve_refuses_without_search_indexes(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    for k, v in BASE.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(doctor, "run_checks", lambda s: [Check("es_indexes", "warn", "alias without an index: x",
                                                               "run kb-core reindex")])
    monkeypatch.setattr("kb_core.serve.app.run", lambda s: pytest.fail("must not start"))
    assert cli.main(["serve"]) == 1
    assert "reindex" in capsys.readouterr().err


def test_mcp_tools_carry_the_configured_rules():
    from kb_core.serve.mcp import build_mcp

    server = build_mcp()
    import asyncio

    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert {"search", "read"} <= set(tools)
    assert "Usage rules:" in tools["search"].description


def test_mcp_registers_all_five_tools_with_kb_parameters():
    import asyncio

    from kb_core.serve.mcp import build_mcp

    tools = {t.name: t for t in asyncio.run(build_mcp().list_tools())}
    assert set(tools) == {"search", "browse", "read", "resolve_concept", "get_metric_series"}
    props = lambda name: set(tools[name].input_schema["properties"])  # noqa: E731
    assert {"doc_id", "node_id", "depth", "tree_source"} <= props("browse")
    assert {"term", "lang_hint", "limit"} <= props("resolve_concept")
    assert {"concept_id", "fiscal_years", "basis", "with_yoy", "include_obs", "entity_scope"} <= props("get_metric_series")
    assert all("Usage rules:" in t.description for t in tools.values())
