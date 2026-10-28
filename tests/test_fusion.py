from kb_core.retrieval.fusion import Candidate, fuse, rrf


def test_rrf_k60_weighted():
    assert rrf({"title_tok": 1, "summary_tok": 3}, {"title_tok", "summary_tok"}) == round(1 / 61 + 1 / 63, 6)
    assert rrf({"title_tok": 1, "concept_tok": 1}, {"title_tok"}) == round(1 / 61, 6)


def test_gate_drops_low_coverage_hits():
    hits = {"title_tok": [("n1", 9.0, {"doc_id": "d"}), ("n2", 8.0, {"doc_id": "d"}), ("n3", 7.0, {"doc_id": "d"})]}
    cov = {"n1": 1.0, "n2": 0.2, "n3": 0.6}
    cands, dropped = fuse(hits, gate=lambda route, node, row: cov[node], threshold=0.5,
                          title_informative=lambda c: True, page_nodes=lambda d, p: [])
    assert set(cands) == {"n1", "n3"} and dropped == {"title_tok": [["n2", 0.2]]}
    assert cands["n3"].fields == {"title_tok": 2}            # ranks recomputed among the kept
    assert cands["n1"].tier == "structure"


def test_page_hit_maps_to_one_deepest_node():
    """kb-core deviation (project owner, 2026-10-27): a page hit counts toward the first deepest covering node in reading
    order only, so a page split into several leaf nodes does not fill the top k with one page."""
    hits = {"page_text_tok": [(("d", 5), 3.0, {"doc_id": "d", "page_no": 5})]}
    cands, _ = fuse(hits, gate=lambda *a: 1.0, threshold=0.5, title_informative=lambda c: False,
                    page_nodes=lambda d, p: ["d:regions:0007", "d:regions:0008"] if p == 5 else [])
    assert set(cands) == {"d:regions:0007"}
    assert all(isinstance(c, Candidate) and c.tier == "text" for c in cands.values())


def test_a_page_hit_goes_to_the_covering_node_that_starts_on_the_page():
    """Round 2 W1 (the project owner's ranking-fix ruling, 2026-10-27): a section continuing from the previous page does not take
    a page hit from the section that starts on that page; without one starting there, the first covering node."""
    from kb_core.retrieval.fusion import owner_first

    start = {"a": 11, "b": 12, "c": 12}
    assert owner_first(["a", "b", "c"], start, 12) == ["b", "c", "a"]
    assert owner_first(["a"], start, 12) == ["a"]
    assert owner_first(["b", "a"], {"a": 10, "b": 11}, 12) == ["b", "a"]
