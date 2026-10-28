import pytest

from kb_core.config import load_settings
from kb_core.doctor import run_checks
from kb_core.pg.migrate import migrate
from tests.conftest import PG_DSN

pytestmark = [pytest.mark.pg, pytest.mark.es]


def test_doctor_live_has_no_fail(pg_conn, es_settings, tmp_path):
    migrate(pg_conn)
    s = load_settings({"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": es_settings.es_url,
                       "KB_CORE_INDEX_PREFIX": "kbtest_", "KB_CORE_DELIVERY_DIR": str(tmp_path),
                       "KB_CORE_STORE_DIR": str(tmp_path / "store")}, env_file=None)
    checks = {c.name: c for c in run_checks(s)}
    assert [c for c in checks.values() if c.level == "fail"] == []
    assert checks["es_analyzer"].level == checks["es_alias"].level == "ok"
    assert checks["pg_migrations"].level == "ok"


def test_doctor_live_flags_pending_migrations(pg_conn, es_settings, tmp_path):
    s = load_settings({"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": es_settings.es_url,
                       "KB_CORE_INDEX_PREFIX": "kbtest_", "KB_CORE_DELIVERY_DIR": str(tmp_path)}, env_file=None)
    checks = {c.name: c for c in run_checks(s)}
    assert checks["pg_migrations"].level == "fail" and "migrate" in checks["pg_migrations"].fix


def test_doctor_warns_on_dangling_alias_and_reindex_swap_restores(es_settings):
    from kb_core.doctor import _es_checks
    from kb_core.es.client import es_client
    from kb_core.es.indexes import alias_name, alias_targets, create_physical, swap_alias

    es = es_client(es_settings)
    for kind in ("node", "page"):
        swap_alias(es, alias_name(es_settings, kind), create_physical(es, es_settings, kind))
    assert {c.name: c.level for c in _es_checks(es_settings)}["es_indexes"] == "ok"
    [live] = alias_targets(es, alias_name(es_settings, "node"))
    es.request("DELETE", f"/{live}")                       # a half-finished rebuild / manual delete
    check = {c.name: c for c in _es_checks(es_settings)}["es_indexes"]
    assert check.level == "warn" and "kbtest_node" in check.detail and "reindex" in check.fix
    swap_alias(es, alias_name(es_settings, "node"), create_physical(es, es_settings, "node"))
    assert {c.name: c.level for c in _es_checks(es_settings)}["es_indexes"] == "ok"


def test_doctor_fails_when_a_concrete_index_takes_the_alias_name(es_settings):
    from kb_core.doctor import _es_checks
    from kb_core.es.client import es_client

    es_client(es_settings).request("PUT", "/kbtest_page")
    check = {c.name: c for c in _es_checks(es_settings)}["es_indexes"]
    assert check.level == "fail" and "kbtest_page" in check.detail
