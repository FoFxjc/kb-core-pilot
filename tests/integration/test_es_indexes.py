from pathlib import Path

import pytest

from kb_core.es.client import EsError, es_client
from kb_core.es.indexes import alias_name, create_physical, orphan_indexes, swap_alias

pytestmark = pytest.mark.es
ZH = (Path(__file__).parents[1] / "fixtures" / "zh_term.txt").read_text().strip()


def test_info_reports_version(es_settings):
    v = es_client(es_settings).info()["version"]["number"]
    assert v.split(".")[0] in ("7", "8", "9")


def test_kb_ws_analyzer_splits_on_whitespace_and_lowercases(es_settings):
    es = es_client(es_settings)
    idx = create_physical(es, es_settings, "node")
    assert es.analyze(idx, "kb_ws", f"NPL {ZH} Ratio") == ["npl", ZH, "ratio"]


def test_swap_alias_is_atomic_and_deletes_old(es_settings):
    es = es_client(es_settings)
    alias = alias_name(es_settings, "page")
    first = create_physical(es, es_settings, "page")
    assert swap_alias(es, alias, first) == []
    second = create_physical(es, es_settings, "page")
    assert swap_alias(es, alias, second) == [first]
    assert list(es.request("GET", f"/_alias/{alias}")) == [second]
    assert es.request("HEAD", f"/{first}", allow_404=True) is None


def test_reindex_recovers_from_orphan_index(es_settings):
    es = es_client(es_settings)
    alias = alias_name(es_settings, "node")
    current = create_physical(es, es_settings, "node")
    swap_alias(es, alias, current)
    orphan = create_physical(es, es_settings, "node")       # a rebuild that died before the swap
    assert orphan_indexes(es, es_settings) == [orphan]
    new = create_physical(es, es_settings, "node")
    removed = swap_alias(es, alias, new)
    assert sorted(removed) == sorted([current, orphan])
    assert orphan_indexes(es, es_settings) == []


def test_error_carries_status(es_settings):
    with pytest.raises(EsError) as e:
        es_client(es_settings).request("GET", "/kbtest_missing/_doc/1")
    assert e.value.status == 404


def test_mapping_fields(es_settings):
    es = es_client(es_settings)
    idx = create_physical(es, es_settings, "page")
    props = es.request("GET", f"/{idx}/_mapping")[idx]["mappings"]["properties"]
    assert props["text_tok"]["analyzer"] == "kb_ws"
    assert props["text"]["index"] is False
    assert props["page_no"]["type"] == "integer"
    assert props["doc_id"]["type"] == "keyword"
