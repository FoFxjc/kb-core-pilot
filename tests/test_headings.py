"""kb_core.eval.headings: a blind judge's heading list on sampled pages against the primary tree (round 2 T1.2)."""

from kb_core.eval.headings import match_headings, norm_title


def _node(title, page, origin="regions", end=None):
    return {"title": title, "start_page": page, "end_page": end or page, "origin": origin}


SHEET = {"doc_id": "doc_a", "seed": 301, "pages": [
    {"page": 10, "headings": [{"title": "Capital Management", "level": 2}, {"title": "Risk-Weighted Assets", "level": 3}]},
    {"page": 11, "headings": []},
    {"page": 12, "headings": [{"title": "2.1 Basis of Preparation", "level": 3}]},
]}


def test_titles_normalise_case_bullets_continued_and_wraps():
    assert norm_title("• Risk-Weighted  Assets (continued)") == norm_title("risk-weighted assets")
    assert norm_title("董事的股份或债券权益 (续)") == norm_title("董事的股份或债券权益")
    assert norm_title("集团一体， 展现优势") == norm_title("集团一体，展现优势")


def test_found_missed_misplaced_and_extra_are_counted_per_document():
    nodes = [_node("Capital Management", 10), _node("Overview (continued)", 10),
             _node("2.1 Basis of Preparation", 13), _node("Highlights", 11)]
    out = match_headings(SHEET, nodes)
    assert out["judged"] == 3 and out["found"] == 1
    assert [m["title"] for m in out["missed"]] == ["Risk-Weighted Assets", "2.1 Basis of Preparation"]
    assert [m["title"] for m in out["misplaced"]] == ["2.1 Basis of Preparation"]
    assert sorted(e["title"] for e in out["extra"]) == ["Highlights", "Overview (continued)"]
    assert out["missed_rate"] == round(2 / 3, 4)


def test_a_wrapped_title_matches_by_prefix():
    nodes = [_node("Reiterating the Value of Operating as", 10), _node("Risk-Weighted Assets", 10)]
    sheet = {"doc_id": "d", "pages": [{"page": 10, "headings": [
        {"title": "Reiterating the Value of Operating as One OCBC Group", "level": 2},
        {"title": "Risk-Weighted Assets", "level": 3}]}]}
    assert match_headings(sheet, nodes)["found"] == 2


def test_contents_group_nodes_are_never_extra_and_unsampled_pages_are_ignored():
    nodes = [_node("Our Performance", 10, origin="toc_group"), _node("Elsewhere", 40)]
    out = match_headings({"doc_id": "d", "pages": [{"page": 10, "headings": []}]}, nodes)
    assert out["extra"] == [] and out["judged"] == 0 and out["missed_rate"] == 0.0


def test_an_unfilled_page_is_an_error():
    import pytest

    with pytest.raises(ValueError):
        match_headings({"doc_id": "d", "pages": [{"page": 10, "headings": None}]}, [])
