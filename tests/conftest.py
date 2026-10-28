import os

import pytest

PG_DSN = os.environ.get("KB_CORE_TEST_PG_DSN")
ES_URL = os.environ.get("KB_CORE_TEST_ES_URL")
SCHEMAS = ("registry", "content", "concept", "fact", "quality", "eval")


@pytest.fixture
def pg_conn():
    """A connection to an empty test database (every kb-core schema dropped first)."""
    if not PG_DSN:
        pytest.skip("KB_CORE_TEST_PG_DSN is not set")
    import psycopg

    with psycopg.connect(PG_DSN, autocommit=True) as conn:
        for schema in SCHEMAS:
            conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.execute("DROP TABLE IF EXISTS public.schema_migrations")
        yield conn

ES7_URL = os.environ.get("KB_CORE_TEST_ES7_URL")


def _es_urls() -> list:
    urls = [pytest.param(ES_URL, id="es")] if ES_URL else []
    if ES7_URL:
        urls.append(pytest.param(ES7_URL, id="es7"))
    return urls or [pytest.param(None, id="no-es")]


@pytest.fixture(params=_es_urls())
def es_settings(request):
    """Settings for a live ES (each configured version), prefix kbtest_; test indexes removed before and after."""
    if request.param is None:
        pytest.skip("KB_CORE_TEST_ES_URL is not set")
    from kb_core.config import load_settings
    from kb_core.es.client import es_client

    s = load_settings({"KB_CORE_PG_DSN": PG_DSN or "postgresql://unused", "KB_CORE_ES_URL": request.param,
                       "KB_CORE_INDEX_PREFIX": "kbtest_"}, env_file=None)
    es = es_client(s)

    def clean():  # by name: ES 8 refuses wildcard deletes (action.destructive_requires_name)
        rows = es.request("GET", "/_cat/indices/kbtest_*", params={"format": "json", "h": "index",
                                                                   "expand_wildcards": "all"})
        for r in rows:
            es.request("DELETE", f"/{r['index']}")

    clean()
    yield s
    clean()
