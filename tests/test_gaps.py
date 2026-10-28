"""Link cap, output budget and gap codes (port of kb service/search.py; api-contract §4.4), on plain dicts."""

from types import SimpleNamespace

import pytest

from kb_core.retrieval import context, search
from kb_core.retrieval.fusion import Candidate, cap_links, order_key


def _link(node_id, group, rank, extra_field=None):
    c = Candidate(node_id, "d", fields={"concept_tok": rank, **(extra_field or {})}, tier="link", group=group,
                  concepts=[{"concept_id": "npl_ratio", "confidence": 1 - rank / 10}])
    return c


def test_link_cap_two_per_group():
    cands = [_link("a", "2025", 1, {"page_text_tok": 1}), _link("b", "2025", 2, {"page_text_tok": 2}),
             _link("c", "2025", 3, {"page_text_tok": 3}), _link("d", "2025", 4), _link("e", "2024", 1)]
    out = cap_links(cands, 2, lambda c: order_key(c, lambda _: 0), lambda c: False)
    by = {c.node_id: c for c in out}
    assert [by[n].tier for n in ("a", "b", "e")] == ["link", "link", "link"]
    assert by["c"].tier == "text" and "concept_tok" not in by["c"].fields and by["c"].demoted_link
    assert "d" not in by                      # it came only from the concept route


def test_facts_bypass_budget():
    fact = {"tier": "fact", "node_id": None, "body": "x " * 20000}
    evidence = [{"tier": "text", "node_id": f"n{i}", "body": "y " * 4000} for i in range(10)]
    results, truncated, gaps = search.fit_budget(evidence, [fact], {"query_terms": []}, [])
    assert truncated and results[0] is fact and 0 < len(results) - 1 < 10
    assert [r["rank"] for r in results] == list(range(1, len(results) + 1))
    assert gaps[-1]["code"] == "truncated"


def test_within_budget_nothing_is_cut():
    results, truncated, gaps = search.fit_budget([{"tier": "text", "body": "short"}], [], {}, [])
    assert not truncated and len(results) == 1 and gaps == []


class _Catalog:
    def __init__(self, docs, accuracy=None):
        self.docs = docs
        self.acc = accuracy or {}

    def parallel_docs(self, d):
        g = self.docs[d]["parallel_group_id"]
        return sorted(x for x, m in self.docs.items() if m["parallel_group_id"] == g and x != d)

    def tree_accuracy(self, d):
        return self.acc.get(d)


def _doc(lang, full=True, sections=None, label="printed"):
    return {"lang": lang, "parallel_group_id": "ocbc|ar|2025", "page_label_source": label,
            "completeness": {"full": full, "sections": sections, "note": "excerpt"}}


@pytest.fixture
def catalog(monkeypatch):
    def use(docs, accuracy=None):
        monkeypatch.setattr(context, "_CURRENT", SimpleNamespace(catalog=_Catalog(docs, accuracy)))
    yield use


def _v(**kw):
    return {"query": "NPL ratio", "lang": "any", "fiscal_years": None, "section_types": None, **kw}


def _res(doc_id):
    return {"tier": "text", "source": {"doc_id": doc_id}}


HC0 = {"lang": {}}


def test_over_filtered_when_filters_remove_every_hit(catalog):
    catalog({"en": _doc("en")}, {"en": 0.9})
    gaps = search._gaps(_v(fiscal_years=[2030]), ["en"], [], HC0, {"lang": {"en": 4}})
    assert [g["code"] for g in gaps] == ["over_filtered"]
    assert gaps[0]["next"][0]["params"] == {"query": "NPL ratio"}


def test_section_missing_in_lang_points_to_the_full_edition(catalog):
    catalog({"en": _doc("en"), "zh": _doc("zh", full=False, sections=["chairman_statement"])}, {"en": 0.9, "zh": 0.9})
    gaps = search._gaps(_v(query="management discussion NPL", lang="zh"), ["zh"], [], {"lang": {"zh": 0}},
                        {"lang": {"en": 3}})
    g = next(g for g in gaps if g["code"] == "section_missing_in_lang")
    assert g["doc_id"] == "zh" and g["next"][0]["params"]["lang"] == "en"


def test_parallel_doc_tree_quality_and_page_label_gaps(catalog):
    catalog({"en": _doc("en", label="none"), "zh": _doc("zh")}, {"en": 0.8})
    codes = [g["code"] for g in search._gaps(_v(lang="en"), ["en"], [_res("en")], {"lang": {"en": 1}},
                                             {"lang": {"en": 1}})]
    assert codes == ["parallel_doc_available", "tree_quality_low", "page_label_unreliable"]


def test_no_gaps_for_a_checked_full_document(catalog):
    catalog({"en": _doc("en")}, {"en": 0.94})
    assert search._gaps(_v(), ["en"], [_res("en")], {"lang": {"en": 1}}, {"lang": {"en": 1}}) == []


def test_concept_gaps():
    assert [g["code"] for g in search.concept_gaps([], [], True)] == ["concept_unknown"]
    assert [g["code"] for g in search.concept_gaps(["npl_ratio"], [{"tier": "text"}], True)] == ["unlinked_text_only"]
    assert search.concept_gaps(["npl_ratio"], [{"tier": "link"}], True) == []
    assert search.concept_gaps([], [], False) == []
