"""`kb-core reindex` (design §3 index, §4.2): rebuild the ES node and page indexes from Postgres only.

Full rebuild: new physical indexes, bulk load, refresh, atomic alias swap (old and orphan indexes deleted).
One document (`--doc`): delete that document's documents behind the aliases and load them again; when the aliases
do not exist yet, a full rebuild is done instead.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field

import psycopg
import psycopg.rows

from kb_core.config import Settings
from kb_core.es.client import EsClient
from kb_core.es.indexes import alias_name, alias_targets, create_physical, swap_alias
from kb_core.queries import es_query, filter_params, pg_query

BATCH = 500
SOURCES = {"node": ("D01_nodes_for_index", lambda r: r["node_id"]),
           "page": ("D02_pages_for_index", lambda r: f"{r['doc_id']}:{r['page_no']}")}


@dataclass
class IndexSummary:
    nodes: int = 0
    pages: int = 0
    full: bool = False
    index_names: dict = field(default_factory=dict)


def _rows(conn: psycopg.Connection, kind: str, doc_id: str | None) -> Iterator[dict]:
    filters = {"doc_id": [doc_id]} if doc_id else {}
    _, sql = pg_query(SOURCES[kind][0], filters=filters)
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(sql, filter_params(filters))
        yield from cur


def _load(conn: psycopg.Connection, es: EsClient, index: str, kind: str, doc_id: str | None) -> int:
    key = SOURCES[kind][1]
    batch, n = [], 0
    for row in _rows(conn, kind, doc_id):
        batch += [{"index": {"_index": index, "_id": key(row)}}, row]
        n += 1
        if len(batch) >= 2 * BATCH:
            es.bulk(batch)
            batch = []
    if batch:
        es.bulk(batch)
    es.request("POST", f"/{index}/_refresh")
    return n


def reindex(conn: psycopg.Connection, es: EsClient, settings: Settings, doc_id: str | None = None) -> IndexSummary:
    out = IndexSummary()
    aliases = {k: alias_name(settings, k) for k in SOURCES}
    if doc_id and all(alias_targets(es, a) for a in aliases.values()):
        for kind, alias in aliases.items():
            es.request("POST", f"/{alias}/_delete_by_query", params={"refresh": "true", "conflicts": "proceed"},
                       json=es_query("D03_delete_doc", {"doc_id": doc_id})[1])
            [target] = alias_targets(es, alias)
            setattr(out, f"{kind}s", _load(conn, es, target, kind, doc_id))
            out.index_names[kind] = target
        return out
    out.full = True
    for kind, alias in aliases.items():
        index = create_physical(es, settings, kind)
        setattr(out, f"{kind}s", _load(conn, es, index, kind, None))
        swap_alias(es, alias, index)
        out.index_names[kind] = index
    return out
