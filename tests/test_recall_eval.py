"""Recall eval hit rules (port of kb scripts/eval.py recall mode)."""

from kb_core.eval import recall


def _r(node_id, doc_id, start, end, tier="text", group=None):
    return {"tier": tier, "node_id": node_id, "group": group, "title": node_id,
            "source": {"doc_id": doc_id, "page_range": [start, end]}}


def _fact():
    return {"tier": "fact", "node_id": None, "group": None, "title": "fact",
            "source": {"doc_id": "d_2025_en", "page_range": [9, 9]}}


GOLD = {"d_2025_en": [100, 105]}


def test_page_hit_needs_overlap_in_the_same_document():
    assert recall.page_hit(_r("n", "d_2025_en", 98, 100), GOLD)
    assert not recall.page_hit(_r("n", "d_2025_en", 101, 104), GOLD)
    assert not recall.page_hit(_r("n", "d_2024_en", 100, 100), GOLD)


def test_evidence_drops_fact_results_and_reranks():
    out = recall.evidence([_fact(), _r("a", "d_2025_en", 1, 1), _r("b", "d_2025_en", 2, 2)])
    assert [(r["node_id"], r["rank"]) for r in out] == [("a", 1), ("b", 2)]


def test_asked_years_from_query_text_else_from_gold_documents():
    assert recall.asked_years({"query": "NPL ratio in 2024 vs 2025?", "gold": {"x_2023_en": [1]}}) == [2024, 2025]
    assert recall.asked_years({"query": "NPL ratio?", "gold": {"ocbc_ar_2023_en": [1], "ocbc_ar_2023_zh": [2]}}) == [2023]


def test_single_reports_first_page_hit_rank_for_both_variants():
    calls = []

    def call(body):
        calls.append(body)
        if body.get("fiscal_years"):
            res = [_fact(), _r("a", "d_2025_en", 1, 2), _r("b", "d_2025_en", 104, 106)]
        else:
            res = [_r("a", "d_2025_en", 1, 2)] * 5 + [_r("b", "d_2025_en", 105, 105)]
        return {"results": res, "trace_id": "t", "scope": {"query_terms": []}}

    row = recall.single(call, {"id": "q", "lang": "en", "query": "NPL 2025", "gold": GOLD}, lambda gold: {"b"})
    assert calls[0] == {"query": "NPL 2025", "limit": 5, "fiscal_years": [2025]}
    assert calls[1] == {"query": "NPL 2025", "limit": 5}
    assert row["with_year"]["page_hit_rank"] == 2 and row["with_year"]["node_hit_rank"] == 2
    assert row["no_year"]["page_hit_rank"] is None      # the hit is 6th, outside the top 5


def test_cross_year_needs_a_hit_in_every_year_group_top3():
    q = {"id": "x", "lang": "en", "query": "NPL 2024 vs 2025", "years": [2024, 2025],
         "gold": {2024: {"d_2024_en": [10]}, 2025: {"d_2025_en": [9]}}}

    def call(body):
        assert body == {"query": q["query"], "group_by": "fiscal_year", "per_group": 3, "limit": 10}
        return {"results": [_r("a", "d_2024_en", 10, 10, group="2024"), _r("b", "d_2025_en", 1, 1, group="2025"),
                            _r("c", "d_2025_en", 2, 2, group="2025"), _r("d", "d_2025_en", 3, 3, group="2025"),
                            _r("e", "d_2025_en", 9, 9, group="2025")],
                "trace_id": "t", "scope": {"query_terms": []}}

    row = recall.cross_year(call, q, lambda gold: set())
    assert row["per_year"][2024]["page"] and not row["per_year"][2025]["page"]   # 2025's hit is 4th in its group
    assert row["page_hit"] is False


def test_summary_counts_only_questions_without_heldout_term():
    single = [{"id": "q1", "with_year": {"page_hit_rank": 1, "node_hit_rank": None},
               "no_year": {"page_hit_rank": None, "node_hit_rank": None}},
              {"id": "h1", "heldout_term": "t", "with_year": {"page_hit_rank": 1, "node_hit_rank": 1},
               "no_year": {"page_hit_rank": 1, "node_hit_rank": 1}}]
    cross = [{"id": "x01", "page_hit": True, "node_hit": False}]
    s = recall.summarize({"single": single, "cross_year": cross}, legacy_ids={"q1"})
    assert s["single"] == {"questions": 1, "with_year": {"node_hit_at5": 0, "page_hit_at5": 1},
                           "no_year": {"node_hit_at5": 0, "page_hit_at5": 0}}
    assert s["cross_year"] == {"questions": 1, "node_hit": 0, "page_hit": 1}
    assert s["x01_page_hit"] is True
    assert s["heldout"] == {"legacy": {"questions": 1, "hits": 1}, "new": {"questions": 1, "hits": 1}}


def test_rows_one_per_variant_and_year():
    out = {"single": [{"id": "q1", "lang": "en", "fiscal_years": [2025], "query": "q",
                       "with_year": {"page_hit_rank": 2, "node_hit_rank": None, "hit_node_ids": ["b"], "top5": [],
                                     "trace_id": "t1", "query_terms": []},
                       "no_year": {"page_hit_rank": None, "node_hit_rank": None, "hit_node_ids": [], "top5": [],
                                   "trace_id": "t2", "query_terms": []}}],
           "cross_year": [{"id": "x", "lang": "en", "query": "q", "trace_id": "t3", "query_terms": [],
                           "per_year": {2024: {"page": True, "node": False, "page_hit_pos": 1, "hit_node_ids": ["a"],
                                               "group_top3": []}}}]}
    rows = recall.result_rows(out)
    assert [(r["question_id"], r["variant"], r["year"], r["hit"], r["best_rank"]) for r in rows] == [
        ("q1", "with_year", 2025, True, 2), ("q1", "no_year", None, False, None), ("x", "crossyear", 2024, True, 1)]
