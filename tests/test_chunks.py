from kb_core.build.chunks import deepest_covering, summary_of
from kb_core.build.tree import TreeNode


def node(i, parent, start, end):
    return TreeNode(f"d:regions:{i:04d}", parent, 1 if parent is None else 2, i, f"T{i}", start, end, "toc", [])


def test_page_covering_nodes_are_deepest():
    nodes = [node(0, None, 1, 4), node(1, "d:regions:0000", 2, 3), node(2, None, 5, 5)]
    cov = deepest_covering(nodes, 6)
    assert cov == {1: ["d:regions:0000"], 2: ["d:regions:0001"], 3: ["d:regions:0001"], 4: ["d:regions:0000"],
                   5: ["d:regions:0002"], 6: []}


def test_summary_is_title_plus_300_after_the_title():
    text = "Header line\nRisk Management\n" + "x" * 500
    s = summary_of("Risk Management", text)
    assert s.startswith("Risk Management x") and len(s) == len("Risk Management ") + 299  # kb: slice includes the space


def test_summary_when_title_not_on_page():
    s = summary_of("Missing Title", "body " * 100)
    assert s.startswith("Missing Title body") and len(s) <= len("Missing Title ") + 300
