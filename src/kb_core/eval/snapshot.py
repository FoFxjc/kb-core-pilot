"""`kb-core eval snapshot`: the database-side regression numbers (fact counts, per-document tree accuracy) as one
JSON-ready dict, compared with `kb-core eval compare` like a recall result."""

import psycopg
from psycopg.rows import dict_row

from kb_core.queries import pg_query

TREE_KEYS = ("value", "correct", "sampled", "seed", "sheet")


def snapshot(conn: psycopg.Connection) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        facts = dict(cur.execute(pg_query("V6_fact_summary")[1]).fetchone())
        tree = {r["doc_id"]: {k: r["value"].get(k) for k in TREE_KEYS}
                for r in cur.execute(pg_query("V7_tree_accuracy")[1]).fetchall()}
    facts["metrics_covered"] = list(facts["metrics_covered"])
    return {"facts": facts, "tree": tree}
