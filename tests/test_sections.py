from kb_core.build.sections import assign
from kb_core.build.tree import Node, flatten
from kb_core.profiles import get

RULES = get("annual_report").sections


def tree():
    return [
        Node("Cover and Contents", 1, 2, "toc_preface"),
        Node("Hear the Views of Our Leaders", 3, 8, "toc_group", nodes=[
            Node("Chin Yee, Group Chief Financial Officer", 3, 4, "toc"),
            Node("Teck Long, Global Wholesale Banking", 5, 6, "toc"),
            Node("Hwee Boon, Group Human Resources", 7, 8, "toc")]),
        Node("Financials", 9, 30, "toc_group", nodes=[
            Node("Management Discussion and Analysis", 9, 12, "toc", nodes=[Node("Overview", 9, 9, "heading")]),
            Node("Financial Statements", 13, 30, "toc", nodes=[
                Node("Income Statements", 13, 13, "subtoc"),
                Node("Notes to the Financial Statements", 14, 30, "subtoc", nodes=[
                    Node("1. General", 14, 15, "note", nodes=[Node("1.1 Scope", 14, 14, "subnote")])])])]),
        Node("Something Else", 31, 32, "toc"),
    ]


def by_title():
    t = tree()
    assign(t, RULES)
    return {n.title: (n.section_type, n.section_rule) for n in flatten(t, "d")}


def test_md_a_rule_and_heading_child_inherits():
    s = by_title()
    assert s["Management Discussion and Analysis"] == ("md_a", "R15")
    assert s["Overview"] == ("md_a", "R15")


def test_notes_children_inherit():
    s = by_title()
    assert s["Notes to the Financial Statements"] == ("notes", "R19")
    assert s["1. General"] == s["1.1 Scope"] == ("notes", "R19")
    assert s["Income Statements"] == ("primary_statements", "R18")


def test_leaders_group_rules():
    s = by_title()
    assert s["Chin Yee, Group Chief Financial Officer"] == ("cfo_review", "R03")
    assert s["Teck Long, Global Wholesale Banking"] == ("business_review", "R04")
    assert s["Hwee Boon, Group Human Resources"] == ("leadership_letters", "R05")
    assert s["Hear the Views of Our Leaders"] == (None, None)       # children disagree


def test_preface_and_unmatched():
    s = by_title()
    assert s["Cover and Contents"] == ("front_matter", "R01")
    assert s["Something Else"] == (None, None)
    assert s["Financial Statements"] == (None, None)
