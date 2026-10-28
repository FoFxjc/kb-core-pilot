"""The retrieval service's shared state: settings, the ES client, one Postgres connection and the catalog.

`init(settings)` once at startup (serve, eval); tools call `current()`. Postgres access is serialised with a lock
(one connection; the service is read-mostly and small).
"""

import threading

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from kb_core.config import Settings
from kb_core.es.client import EsClient, es_client
from kb_core.es.indexes import alias_name
from kb_core.pg.db import connect
from kb_core.queries import es_query, filter_params, pg_query


class Context:
    def __init__(self, settings: Settings):
        from kb_core.retrieval.catalog import Catalog

        self.settings = settings
        self.es: EsClient = es_client(settings)
        self.pg: psycopg.Connection = connect(settings)
        self.lock = threading.RLock()
        self.catalog = Catalog(self)

    def es_search(self, kind: str, template: str, params: dict, log: dict | None = None) -> list[dict]:
        return self.es_raw(kind, template, params, log)["hits"]["hits"]

    def es_raw(self, kind: str, template: str, params: dict, log: dict | None = None) -> dict:
        tid, body = es_query(template, params)
        if log is not None:
            log[tid] = body
        return self.es.request("POST", f"/{alias_name(self.settings, kind)}/_search", json=body)

    def pg_rows(self, name: str, params: dict | None = None, filters: dict | None = None,
                limit: int | None = None, log: dict | None = None) -> list[dict]:
        tid, sql = pg_query(name, filters=filters, limit=limit)
        args = dict(params or {}, **filter_params(filters or {}))
        if log is not None:
            log[tid] = {"sql": sql, "params": {k: v for k, v in args.items()}}
        with self.lock, self.pg.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, args)
            return cur.fetchall() if cur.description else []

    def pg_execute(self, name: str, params: dict) -> None:
        _, sql = pg_query(name)
        args = {k: (Jsonb(v) if isinstance(v, (dict, list)) and k in ("input", "output", "detail") else v)
                for k, v in params.items()}
        with self.lock:
            self.pg.execute(sql, args)

    def close(self) -> None:
        self.es.close()
        self.pg.close()


_CURRENT: Context | None = None


def init(settings: Settings) -> Context:
    global _CURRENT
    from kb_core.config import use

    close()
    use(settings)
    _CURRENT = Context(settings)
    _CURRENT.catalog.refresh()
    return _CURRENT


def current() -> Context:
    if _CURRENT is None:
        raise RuntimeError("retrieval context not initialised (call kb_core.retrieval.context.init)")
    return _CURRENT


def close() -> None:
    global _CURRENT
    if _CURRENT is not None:
        _CURRENT.close()
        _CURRENT = None
