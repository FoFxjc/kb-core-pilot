"""kb_core.eval.compare: regression check of a recall run against a baseline run (round 2 T0.3)."""

import copy

from kb_core.eval.compare import compare


def _hit(rank, top):
    return {"node_hit_rank": rank, "page_hit_rank": rank, "top5": top}


TOP = [[1, "link", "doc_a", [98, 100], "Overview", "doc_a:regions:0294"],
       [2, "text", "doc_a", [100, 100], "Allowances", "doc_a:regions:0296"]]

BASE = {
    "summary": {"single": {"questions": 1, "with_year": {"node_hit_at5": 1, "page_hit_at5": 1},
                           "no_year": {"node_hit_at5": 1, "page_hit_at5": 1}},
                "cross_year": {"questions": 1, "node_hit": 1, "page_hit": 1}, "x01_page_hit": True,
                "heldout": {"legacy": {"questions": 0, "hits": 0}, "new": {"questions": 0, "hits": 0}}},
    "single": [{"id": "q01", "with_year": _hit(1, TOP), "no_year": _hit(2, TOP)}],
    "cross_year": [{"id": "x01", "node_hit": True, "page_hit": True,
                    "per_year": {"2025": {"group_top3": TOP}}}],
}


def test_identical_runs_have_no_regression_and_no_differences():
    out = compare(BASE, copy.deepcopy(BASE))
    assert out["regressions"] == []
    assert out["topk_changed"] == []
    assert out["rank_changes"] == []


def test_renumbered_node_ids_alone_do_not_count_as_a_topk_change():
    new = copy.deepcopy(BASE)
    for row in new["single"][0]["with_year"]["top5"]:
        row[5] = row[5].replace("029", "039")
    assert compare(BASE, new)["topk_changed"] == []


def test_a_lower_summary_count_is_a_regression():
    new = copy.deepcopy(BASE)
    new["summary"]["single"]["no_year"]["node_hit_at5"] = 0
    out = compare(BASE, new)
    assert out["regressions"] == [{"metric": "single.no_year.node_hit_at5", "base": 1, "new": 0}]


def test_a_higher_count_is_an_improvement_not_a_regression():
    new = copy.deepcopy(BASE)
    base = copy.deepcopy(BASE)
    base["summary"]["cross_year"]["node_hit"] = 0
    out = compare(base, new)
    assert out["regressions"] == []
    assert out["improvements"] == [{"metric": "cross_year.node_hit", "base": 0, "new": 1}]


def test_rank_and_topk_changes_are_listed_per_question():
    new = copy.deepcopy(BASE)
    new["single"][0]["no_year"] = _hit(4, list(reversed(TOP)))
    out = compare(BASE, new)
    assert out["rank_changes"] == [{"id": "q01", "variant": "no_year", "field": "node_hit_rank", "base": 2, "new": 4},
                                   {"id": "q01", "variant": "no_year", "field": "page_hit_rank", "base": 2, "new": 4}]
    assert out["topk_changed"] == ["q01/no_year"]


def test_a_question_missing_from_the_new_run_is_a_regression():
    new = copy.deepcopy(BASE)
    new["cross_year"] = []
    out = compare(BASE, new)
    assert {"metric": "missing_question", "id": "x01"} in out["regressions"]


def test_fewer_questions_in_a_summary_block_is_a_regression():
    new = copy.deepcopy(BASE)
    new["summary"]["cross_year"]["questions"] = 0
    assert {"metric": "cross_year.questions", "base": 1, "new": 0} in compare(BASE, new)["regressions"]


def test_a_lost_hit_is_a_regression_even_when_the_totals_are_unchanged():
    base = copy.deepcopy(BASE)
    base["single"].append({"id": "q02", "with_year": _hit(None, TOP), "no_year": _hit(None, TOP)})
    new = copy.deepcopy(base)
    new["single"][0]["no_year"] = _hit(None, TOP)   # q01 loses its no_year hit
    new["single"][1]["no_year"] = _hit(3, TOP)      # q02 gains one: totals unchanged
    regressions = compare(base, new)["regressions"]
    assert {"metric": "lost_hit", "id": "q01", "variant": "no_year", "field": "node_hit_rank"} in regressions


def test_a_lost_cross_year_hit_is_a_regression():
    new = copy.deepcopy(BASE)
    new["cross_year"][0]["node_hit"] = False
    assert {"metric": "lost_hit", "id": "x01", "variant": "cross_year", "field": "node_hit"} in \
        compare(BASE, new)["regressions"]


# --- fact counts and tree accuracy (eval snapshot files) ---

FACTS = {"observations": 408, "facts": 89, "agreed": 83, "single": 6, "conflict": 0,
         "metrics_covered": ["net_profit", "nii"]}
TREE = {"doc_a": {"value": 0.85, "correct": 34, "sampled": 40}, "doc_b": {"value": 0.9, "correct": 36, "sampled": 40}}


def test_identical_snapshots_pass():
    snap = {"facts": FACTS, "tree": TREE}
    assert compare(snap, copy.deepcopy(snap))["regressions"] == []


def test_fewer_agreed_facts_or_a_new_conflict_is_a_regression():
    new = copy.deepcopy({"facts": FACTS})
    new["facts"].update(agreed=82, conflict=1)
    regressions = compare({"facts": FACTS}, new)["regressions"]
    assert {"metric": "facts.agreed", "base": 83, "new": 82} in regressions
    assert {"metric": "facts.conflict", "base": 0, "new": 1} in regressions


def test_a_metric_no_longer_covered_is_a_regression():
    new = copy.deepcopy({"facts": FACTS})
    new["facts"]["metrics_covered"] = ["net_profit"]
    assert {"metric": "facts.metrics_covered", "missing": ["nii"]} in compare({"facts": FACTS}, new)["regressions"]


def test_lower_tree_accuracy_on_one_document_is_a_regression():
    new = copy.deepcopy({"tree": TREE})
    new["tree"]["doc_b"]["value"] = 0.875
    new["tree"]["doc_a"]["value"] = 0.95
    out = compare({"tree": TREE}, new)
    assert out["regressions"] == [{"metric": "tree.doc_b", "base": 0.9, "new": 0.875}]
    assert {"metric": "tree.doc_a", "base": 0.85, "new": 0.95} in out["improvements"]


def test_a_document_without_tree_accuracy_is_a_regression():
    new = copy.deepcopy({"tree": TREE})
    del new["tree"]["doc_b"]
    assert {"metric": "tree.doc_b", "base": 0.9, "new": None} in compare({"tree": TREE}, new)["regressions"]


# --- explained exceptions: only approved lost node hits are waived ---

def _lost_q01_node_hit():
    base = copy.deepcopy(BASE)
    new = copy.deepcopy(BASE)
    new["single"][0]["no_year"]["node_hit_rank"] = None
    new["summary"]["single"]["no_year"]["node_hit_at5"] = 0
    return base, new


def test_an_approved_lost_node_hit_is_waived_with_its_summary_drop():
    base, new = _lost_q01_node_hit()
    exc = [{"id": "q01", "variant": "no_year", "field": "node_hit_rank",
            "reason": "gold node split into two leaves by the W1 tree fix", "approved_by": "project-owner", "pr": 7}]
    out = compare(base, new, exceptions=exc, pr=7)
    assert out["regressions"] == []
    assert [w["id"] for w in out["waived"]] == ["q01"]
    assert {"metric": "single.no_year.node_hit_at5", "base": 1, "new": 0} in out["waived_counts"]


def test_an_exception_without_approval_waives_nothing():
    base, new = _lost_q01_node_hit()
    exc = [{"id": "q01", "variant": "no_year", "field": "node_hit_rank", "reason": "tree split", "pr": 7}]
    out = compare(base, new, exceptions=exc, pr=7)
    assert {"metric": "lost_hit", "id": "q01", "variant": "no_year", "field": "node_hit_rank"} in out["regressions"]
    assert {"metric": "single.no_year.node_hit_at5", "base": 1, "new": 0} in out["regressions"]
    assert out["pending_exceptions"] == exc


def test_a_lost_page_hit_cannot_be_waived():
    base, new = _lost_q01_node_hit()
    new["single"][0]["no_year"]["page_hit_rank"] = None
    exc = [{"id": "q01", "variant": "no_year", "field": "page_hit_rank", "reason": "x", "approved_by": "project-owner", "pr": 7}]
    out = compare(base, new, exceptions=exc, pr=7)
    assert {"metric": "lost_hit", "id": "q01", "variant": "no_year", "field": "page_hit_rank"} in out["regressions"]


# --- review fixes (PR #11) ---

def test_a_tree_value_from_a_different_sample_is_flagged_for_review():
    new = copy.deepcopy({"tree": TREE})
    new["tree"]["doc_a"].update(seed=201, sheet="tree_doc_a_201.judged.yaml")
    base = copy.deepcopy({"tree": TREE})
    base["tree"]["doc_a"].update(seed=105, sheet="tree_doc_a_105.judged.yaml")
    out = compare(base, new)
    assert {"metric": "tree.doc_a", "reason": "different sample", "base": [105, "tree_doc_a_105.judged.yaml", 40],
            "new": [201, "tree_doc_a_201.judged.yaml", 40]} in out["review"]


def test_a_missing_tree_value_in_the_baseline_does_not_crash():
    base = {"tree": {"doc_a": {"value": None}}}
    assert compare(base, {"tree": {"doc_a": {"value": 0.5}}})["regressions"] == []


def test_more_single_facts_or_a_restated_change_is_flagged_for_review():
    new = copy.deepcopy({"facts": {**FACTS, "restated": 0}})
    new["facts"].update(facts=94, single=11, restated=1)
    out = compare({"facts": {**FACTS, "restated": 0}}, new)
    assert {"metric": "facts.single", "base": 6, "new": 11} in out["review"]
    assert {"metric": "facts.restated", "base": 0, "new": 1} in out["review"]


def test_a_baseline_without_a_known_block_is_an_error():
    import pytest

    with pytest.raises(ValueError):
        compare({"commands": []}, {"facts": FACTS})


def test_an_exception_for_another_pr_waives_nothing_and_unused_ones_are_listed():
    base, new = _lost_q01_node_hit()
    exc = [{"id": "q01", "variant": "no_year", "field": "node_hit_rank", "reason": "split", "approved_by": "project-owner",
            "pr": 12},
           {"id": "zz99", "variant": "no_year", "field": "node_hit_rank", "reason": "x", "approved_by": "project-owner",
            "pr": 13}]
    out = compare(base, new, exceptions=exc, pr=13)
    assert {"metric": "lost_hit", "id": "q01", "variant": "no_year", "field": "node_hit_rank"} in out["regressions"]
    assert out["unused_exceptions"] == [exc[1]]
    assert out["other_pr_exceptions"] == [exc[0]]


def test_a_malformed_exception_is_pending_not_a_crash():
    base, new = _lost_q01_node_hit()
    out = compare(base, new, exceptions=[{"reason": "x", "approved_by": "project-owner"}], pr=1)
    assert out["pending_exceptions"] == [{"reason": "x", "approved_by": "project-owner"}]


def test_a_lost_page_hit_is_waived_only_with_an_explicit_page_hit_approval():
    base, new = _lost_q01_node_hit()
    new["single"][0]["no_year"]["page_hit_rank"] = None
    new["summary"]["single"]["no_year"]["page_hit_at5"] = 0
    common = {"id": "q01", "variant": "no_year", "reason": "rank boundary after tree fix", "approved_by": "project-owner",
              "pr": 9}
    exc = [{**common, "field": "node_hit_rank"}, {**common, "field": "page_hit_rank", "page_hit": True}]
    out = compare(base, new, exceptions=exc, pr=9)
    assert out["regressions"] == []
    assert {w["field"] for w in out["waived"]} == {"node_hit_rank", "page_hit_rank"}
