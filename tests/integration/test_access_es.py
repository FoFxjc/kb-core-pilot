"""Round 2 W3 T3.4: the ES access filter returns exactly what the policy allows (live ES 8 and 7.10)."""

import itertools
from datetime import UTC, datetime

import pytest

from kb_core.access.policy import CLASSIFICATIONS, Access, decide, filter_terms, load_roles
from kb_core.access.routes import es_access_filter
from kb_core.es.client import es_client
from kb_core.es.indexes import create_physical

pytestmark = pytest.mark.es

BEFORE = datetime(2026, 11, 1, tzinfo=UTC)
AFTER = datetime(2026, 12, 1, tzinfo=UTC)
EMBARGO = "2026-11-15T00:00:00+08:00"


def _docs():
    out = []
    for i, (cls, domains, embargo) in enumerate(itertools.product(
            CLASSIFICATIONS, ([], ["finance"], ["hr"]), (None, EMBARGO))):
        out.append({"node_id": f"n{i:03d}", "doc_id": "d", "title_tok": "x", "access_classification": cls,
                    "access_domains": domains, "access_embargo_until": embargo})
    return out


def test_es_filter_agrees_with_decide_for_every_role_label_and_time(es_settings):
    es = es_client(es_settings)
    idx = create_physical(es, es_settings, "node")
    docs = _docs()
    es.bulk([x for d in docs for x in ({"index": {"_index": idx, "_id": d["node_id"]}}, d)])
    es.request("POST", f"/{idx}/_refresh")
    for role, subject in load_roles().items():
        for now in (BEFORE, AFTER):
            q = {"size": 100, "_source": ["node_id"],
                 "query": {"bool": {"filter": es_access_filter(filter_terms(subject, now))}}}
            got = {h["_source"]["node_id"] for h in es.request("POST", f"/{idx}/_search", json=q)["hits"]["hits"]}
            want = {d["node_id"] for d in docs
                    if decide(subject, Access(d["access_classification"], tuple(d["access_domains"]), "o",
                                              datetime.fromisoformat(d["access_embargo_until"])
                                              if d["access_embargo_until"] else None), now).allow}
            assert got == want, (role, now)
