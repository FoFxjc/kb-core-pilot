"""Identity for many users (enterprise readiness B): auth modes, gateway headers, role map, the HTTP gate."""

import pytest
from fastapi.testclient import TestClient

from kb_core.access.identity import identify, require_admin, require_reader
from kb_core.config import ConfigError, load_settings
from kb_core.retrieval.core import ApiError

BASE = {"KB_CORE_PG_DSN": "postgresql://unused", "KB_CORE_ES_URL": "http://unused"}
GATEWAY = {**BASE, "KB_CORE_ENV": "production", "KB_CORE_AUTH_MODE": "trusted_header",
           "KB_CORE_AUTH_USER_HEADER": "X-Auth-User", "KB_CORE_AUTH_GROUPS_HEADER": "X-Auth-Groups"}


@pytest.fixture
def role_map(tmp_path):
    p = tmp_path / "role_map.yaml"
    p.write_text("version: 1\ngroups:\n  staff: public\n  fin: finance_analyst\n  fin-conf: finance_confidential\n"
                 "admin_groups: [kb-admins]\n")
    return p


@pytest.fixture
def gw(role_map):
    return load_settings({**GATEWAY, "KB_CORE_ACCESS_ROLE_MAP": str(role_map)}, env_file=None)


def code(fn, *a) -> str:
    with pytest.raises(ApiError) as e:
        fn(*a)
    return e.value.code


# --- settings ---------------------------------------------------------------------------------------------------------

def test_production_refuses_auth_mode_none():
    with pytest.raises(ConfigError, match="AUTH_MODE=none"):
        load_settings({**BASE, "KB_CORE_ENV": "production"}, env_file=None)


@pytest.mark.parametrize("clock", [{"KB_CORE_ALLOW_CLOCK_OVERRIDE": "true"},
                                   {"KB_CORE_NOW": "2030-01-01T00:00:00Z"},
                                   {"KB_CORE_ALLOW_CLOCK_OVERRIDE": "true", "KB_CORE_NOW": "2030-01-01T00:00:00Z"}])
def test_production_refuses_the_test_clock(clock):
    with pytest.raises(ConfigError, match="test clock"):
        load_settings({**GATEWAY, **clock}, env_file=None)


@pytest.mark.parametrize("var", ["KB_CORE_LLM_API_KEY_VAR", "KB_CORE_CHAT_API_KEY_VAR", "KB_CORE_JUDGE_API_KEY_VAR",
                                 "KB_CORE_EXTRACT_API_KEY_VAR"])
def test_a_key_variable_outside_kb_core_is_refused(var):
    for env in (BASE, GATEWAY):
        with pytest.raises(ConfigError, match=var):
            load_settings({**env, var: "OTHER_API_KEY"}, env_file=None)


def test_trusted_header_needs_the_user_header():
    with pytest.raises(ConfigError, match="KB_CORE_AUTH_USER_HEADER"):
        load_settings({**BASE, "KB_CORE_AUTH_MODE": "trusted_header"}, env_file=None)


def test_development_without_identity_binds_only_to_loopback():
    with pytest.raises(ConfigError, match="loopback"):
        load_settings({**BASE, "KB_CORE_HOST": "0.0.0.0"}, env_file=None)
    assert load_settings({**GATEWAY, "KB_CORE_HOST": "10.0.0.5"}, env_file=None).host == "10.0.0.5"


def test_env_and_auth_mode_values_are_checked():
    with pytest.raises(ConfigError, match="KB_CORE_ENV"):
        load_settings({**BASE, "KB_CORE_ENV": "prod"}, env_file=None)
    with pytest.raises(ConfigError, match="KB_CORE_AUTH_MODE"):
        load_settings({**BASE, "KB_CORE_AUTH_MODE": "oidc"}, env_file=None)


# --- identify ---------------------------------------------------------------------------------------------------------

def test_mode_none_uses_the_demo_subject():
    s = load_settings(BASE, env_file=None)
    assert identify({}, s).role is None and identify({}, s).user is None
    assert identify({"x-kb-subject": "finance_analyst"}, s).role == "finance_analyst"
    assert identify({}, s, "finance_confidential").role == "finance_confidential"
    assert code(identify, {"x-kb-subject": "root"}, s) == "INVALID_PARAM"


def test_gateway_rejects_x_kb_subject(gw):
    headers = {"x-auth-user": "u1", "x-auth-groups": "fin", "x-kb-subject": "full_access"}
    assert code(identify, headers, gw) == "INVALID_PARAM"
    assert code(identify, {"x-auth-user": "u1", "x-auth-groups": "fin"}, gw, "full_access") == "INVALID_PARAM"


@pytest.mark.parametrize("headers", [{}, {"x-auth-groups": "fin"}, {"x-auth-user": "  ", "x-auth-groups": "fin"}])
def test_gateway_without_a_user_is_401_never_public(gw, headers):
    with pytest.raises(ApiError) as e:
        identify(headers, gw)
    assert e.value.code == "UNAUTHENTICATED" and e.value.http_status == 401


def test_a_user_without_a_mapped_group_is_403(gw):
    with pytest.raises(ApiError) as e:
        identify({"x-auth-user": "u1", "x-auth-groups": "sales, unknown"}, gw)
    assert e.value.code == "FORBIDDEN" and e.value.http_status == 403


def test_the_highest_clearance_role_is_used_and_roles_are_not_combined(gw):
    who = identify({"x-auth-user": "u1", "x-auth-groups": "staff, fin-conf ,fin"}, gw)
    assert who.user == "u1" and who.role == "finance_confidential" and not who.admin
    assert who.roles == ("finance_analyst", "finance_confidential", "public")


def test_admin_comes_from_admin_groups_and_gives_no_data_role(gw):
    who = identify({"x-auth-user": "ops", "x-auth-groups": "kb-admins"}, gw)
    assert who.admin and who.role is None
    require_admin(who)
    assert code(require_reader, who) == "FORBIDDEN"
    assert code(require_admin, identify({"x-auth-user": "u1", "x-auth-groups": "fin"}, gw)) == "FORBIDDEN"


def test_role_map_naming_an_unknown_role_is_refused(tmp_path):
    from kb_core.access.identity import role_map

    p = tmp_path / "bad.yaml"
    p.write_text("groups: {g: superuser}\n")
    s = load_settings({**GATEWAY, "KB_CORE_ACCESS_ROLE_MAP": str(p)}, env_file=None)
    with pytest.raises(ValueError, match="superuser"):
        role_map(s)


def test_the_shipped_role_map_loads():
    from kb_core.access.identity import role_map

    rm = role_map(load_settings(GATEWAY, env_file=None))
    assert rm.groups and rm.admin_groups


# --- the HTTP gate (before any route, MCP included) -------------------------------------------------------------------

@pytest.fixture
def app_client(gw):
    from kb_core.serve.app import create_app

    return TestClient(create_app(gw), base_url="http://127.0.0.1:8200")     # no lifespan: no stores needed


@pytest.mark.parametrize("method,path", [("POST", "/v1/search"), ("GET", "/v1/read"), ("POST", "/mcp"),
                                         ("GET", "/v1/admin/config"), ("POST", "/v1/admin/import"),
                                         ("GET", "/v1/docs/d/pages/1.png"), ("GET", "/ui/chat")])
def test_gate_answers_401_without_a_gateway_user(app_client, method, path):
    r = app_client.request(method, path, json={})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_gate_rejects_x_kb_subject_and_the_subject_query(app_client):
    user = {"X-Auth-User": "u1", "X-Auth-Groups": "fin"}
    r = app_client.post("/v1/search", json={"query": "x"}, headers={**user, "X-KB-Subject": "full_access"})
    assert r.status_code == 400 and r.json()["error"]["details"]["param"] == "X-KB-Subject"
    assert app_client.get("/v1/docs/d/pages/1.png?subject=full_access", headers=user).status_code == 400


@pytest.mark.parametrize("path", ["/v1/admin/config", "/v1/admin/traces", "/v1/admin/docs"])
def test_admin_endpoints_need_the_admin_role(app_client, path):
    r = app_client.get(path, headers={"X-Auth-User": "u1", "X-Auth-Groups": "fin-conf"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    r = app_client.post("/v1/admin/import", json={}, headers={"X-Auth-User": "u1", "X-Auth-Groups": "fin-conf"})
    assert r.status_code == 403


def test_admin_alone_cannot_call_data_tools_or_mcp(app_client):
    admin = {"X-Auth-User": "ops", "X-Auth-Groups": "kb-admins"}
    assert app_client.post("/v1/search", json={"query": "x"}, headers=admin).status_code == 403
    assert app_client.post("/mcp", json={}, headers=admin).status_code == 403


def test_mode_none_has_no_gate():
    from kb_core.serve.app import create_app

    c = TestClient(create_app(load_settings(BASE, env_file=None)), base_url="http://127.0.0.1:8200")
    assert c.get("/v1/nope").status_code == 404          # reaches the routes (no 401)


# --- review of PR #17: one identity per request ---------------------------------------------------------------------

def _raw(app, headers: list[tuple[bytes, bytes]], path: str = "/v1/search"):
    """Call the ASGI app with exactly these header lines (duplicates kept as separate lines)."""
    import asyncio

    sent = []

    async def receive():
        return {"type": "http.request", "body": b'{"query":"x"}', "more_body": False}

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "method": "POST", "path": path, "raw_path": path.encode(), "query_string": b"",
             "headers": [(b"host", b"127.0.0.1:8200"), (b"content-type", b"application/json"), *headers],
             "scheme": "http", "server": ("127.0.0.1", 8200), "client": ("127.0.0.1", 1), "http_version": "1.1",
             "root_path": ""}
    asyncio.run(app(scope, receive, send))
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


@pytest.mark.parametrize("lines", [
    [(b"x-auth-user", b"victim"), (b"x-auth-groups", b"fin-conf"), (b"x-auth-user", b"attacker")],
    [(b"x-auth-user", b"u1"), (b"x-auth-groups", b"staff"), (b"x-auth-groups", b"fin-conf")],
])
def test_a_repeated_identity_header_is_refused(gw, lines):
    from kb_core.serve.app import create_app

    assert _raw(create_app(gw), lines) == 400


def test_a_user_value_with_a_comma_is_refused(gw):
    assert code(identify, {"x-auth-user": "victim, attacker", "x-auth-groups": "fin"}, gw) == "INVALID_PARAM"


def test_identify_refuses_repeated_headers_given_as_starlette_headers(gw):
    from starlette.datastructures import Headers

    h = Headers(raw=[(b"x-auth-user", b"victim"), (b"x-auth-user", b"attacker"), (b"x-auth-groups", b"fin")])
    assert code(identify, h, gw) == "INVALID_PARAM"
