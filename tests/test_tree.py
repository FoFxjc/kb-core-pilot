import pytest

from kb_core.build.tree import body_colour, build_annual_report_tree, build_generic_tree, flatten
from kb_core.profiles import get as get_profile
from tests.tree_helpers import DOC, page, region, view

RULES = get_profile("annual_report").tree_rules


def contents_page():
    """Page 2: contents. Entries: Overview p3 (printed 1), Notes p5 (printed 3), Shareholder Info p9 (printed 7),
    Corporate Info p10 (printed 8), Glossary p11 (printed 9)."""
    return [region(2, 1, "Overview", "text", 9, False, y=300), region(2, 2, "1", "text", 9, False, x=281, y=300, w=5),
            region(2, 5, "Notes to the Financial Statements", "text", 9, False, y=324),
            region(2, 6, "3", "text", 9, False, x=281, y=324, w=5),
            region(2, 7, "Shareholder Info", "text", 9, False, y=336),
            region(2, 8, "7", "text", 9, False, x=281, y=336, w=5),
            region(2, 9, "Corporate Info", "text", 9, False, y=348),
            region(2, 10, "8", "text", 9, False, x=281, y=348, w=5),
            region(2, 11, "Glossary", "text", 9, False, y=360),
            region(2, 12, "9", "text", 9, False, x=281, y=360, w=5)]


def pages(n=11, short=()):
    out = [page(i, "" if i < 3 else str(i - 2)) for i in range(1, n + 1)]
    for i in short:
        out[i - 1]["text"] = "Divider"
    return out


def titles(nodes):
    return [(n.title, n.page_start, n.page_end, n.depth) for n in nodes]


def test_divider_page_moves_to_next_section():
    # page 4 is a short divider page at the end of Overview's range: it belongs to the section that follows it
    regs = contents_page()
    nodes = flatten(build_annual_report_tree(view(pages(short=(4,)), regs), RULES), DOC)
    top = {n.title: (n.page_start, n.page_end) for n in nodes if n.depth == 1}
    assert top["Cover and Contents"] == (1, 2)
    assert top["Overview"] == (3, 3)
    assert top["Notes to the Financial Statements"] == (4, 8)
    assert top["Corporate Info"] == (10, 10)


def test_note_numbering_must_be_consecutive():
    regs = contents_page() + [region(5, 1, "1.\nGeneral"), region(5, 2, "7.\nStray", y=300),
                              region(6, 1, "2.\nBasis"), region(7, 1, "3.\nIncome"), region(7, 2, "4.\nTax", y=400),
                              region(8, 1, "5.\nCapital")]
    nodes = flatten(build_annual_report_tree(view(pages(), regs), RULES), DOC)
    notes = [n.title for n in nodes if n.origin == "note"]
    assert notes == ["1. General", "2. Basis", "3. Income", "4. Tax", "5. Capital"]
    tax = next(n for n in nodes if n.title == "4. Tax")
    income = next(n for n in nodes if n.title == "3. Income")
    assert (income.page_start, income.page_end) == (7, 7) and tax.page_start == 7


def test_continued_note_heading_skipped():
    regs = contents_page() + [region(5, 1, "1.\nGeneral"), region(6, 1, "1.\nGeneral (continued)"),
                              region(6, 2, "2.\nBasis", y=300), region(7, 1, "3.\nIncome"), region(7, 2, "4.\nTax", y=400),
                              region(8, 1, "5.\nCapital")]
    nodes = flatten(build_annual_report_tree(view(pages(), regs), RULES), DOC)
    general = next(n for n in nodes if n.title == "1. General")
    assert (general.page_start, general.page_end) == (5, 6)
    assert not any("continued" in n.title for n in nodes)


def test_note_heading_uses_colour_when_present():
    red, black = "#df271c", "#000000"
    body = [region(5, 9, "body text", "text", 9, False, y=600, color=black)] * 3
    regs = contents_page() + body + [region(5, 1, "1.\nGeneral", color=red), region(5, 2, "2.\nA list item", color=black, y=300),
                                     region(6, 1, "2.\nBasis", color=red), region(7, 1, "3.\nIncome", color=red),
                                     region(7, 2, "4.\nTax", color=red, y=400), region(8, 1, "5.\nCapital", color=red)]
    assert body_colour(regs) == black
    nodes = flatten(build_annual_report_tree(view(pages(), regs), RULES), DOC)
    assert [n.title for n in nodes if n.origin == "note"] == ["1. General", "2. Basis", "3. Income", "4. Tax",
                                                               "5. Capital"]


def test_note_rule_without_colour_field():
    regs = contents_page() + [region(5, 1, "1.\nGeneral"), region(6, 1, "2.\nBasis"), region(7, 1, "3.\nIncome"),
                              region(7, 2, "4.\nTax", y=400), region(8, 1, "5.\nCapital")]
    assert body_colour(regs) is None
    nodes = flatten(build_annual_report_tree(view(pages(), regs), RULES), DOC)
    assert len([n for n in nodes if n.origin == "note"]) == 5


def test_subnotes_under_their_note():
    regs = contents_page() + [region(5, 1, "1.\nGeneral"), region(5, 2, "1.1\nScope", size=10, y=200),
                              region(5, 3, "1.2\nBasis of preparation", size=10, y=400),
                              region(6, 1, "2.\nBasis"), region(7, 1, "3.\nIncome"), region(7, 2, "4.\nTax", y=400),
                              region(8, 1, "5.\nCapital")]
    nodes = flatten(build_annual_report_tree(view(pages(), regs), RULES), DOC)
    general = next(n for n in nodes if n.title == "1. General")
    subs = [n for n in nodes if n.parent_id == general.node_id]
    assert [n.title for n in subs] == ["1.1 Scope", "1.2 Basis of preparation"]


def test_section_headings_nest_by_font_size():
    regs = contents_page() + [region(3, 1, "Business Review", size=20, bold=False, y=60),
                              region(3, 2, "Retail Banking", size=13, y=200),
                              region(3, 3, "Digital channels", size=10, y=300),
                              region(3, 4, "Wealth Management", size=13, y=500)]
    nodes = flatten(build_annual_report_tree(view(pages(), regs), RULES), DOC)
    by = {n.title: n for n in nodes}
    overview = by["Overview"]
    assert by["Retail Banking"].parent_id in (overview.node_id, by["Business Review"].node_id)
    assert by["Digital channels"].parent_id == by["Retail Banking"].node_id
    assert by["Wealth Management"].parent_id == by["Retail Banking"].parent_id


def test_repeated_field_labels_dropped():
    regs = contents_page() + [region(9, 1, "Academic Qualifications", size=10, y=100),
                              region(9, 2, "Academic Qualifications", size=10, y=400),
                              region(9, 3, "Board Committees", size=10, y=600)]
    nodes = flatten(build_annual_report_tree(view(pages(), regs), RULES), DOC)
    assert "Academic Qualifications" not in [n.title for n in nodes]


def test_generic_levels_from_font_size():
    regs = [region(1, 1, "Report", size=20), region(1, 2, "Part A", size=14, y=200),
            region(2, 1, "Detail", size=10), region(3, 1, "Part B", size=14)]
    nodes = flatten(build_generic_tree(view([page(1), page(2), page(3)], regs, doc_type="generic"),
                                       get_profile("generic").tree_rules), DOC)
    by = {n.title: n for n in nodes}
    assert by["Part A"].parent_id == by["Report"].node_id
    assert by["Detail"].parent_id == by["Part A"].node_id
    assert by["Part B"].parent_id == by["Report"].node_id
    assert (by["Part A"].page_start, by["Part A"].page_end) == (1, 2)


def test_node_ids_preorder_stable():
    regs = contents_page() + [region(5, 1, "1.\nGeneral"), region(6, 1, "2.\nBasis"), region(7, 1, "3.\nIncome"),
                              region(7, 2, "4.\nTax", y=400), region(8, 1, "5.\nCapital")]
    a = flatten(build_annual_report_tree(view(pages(), regs), RULES), DOC)
    b = flatten(build_annual_report_tree(view(pages(), regs), RULES), DOC)
    assert [(n.node_id, n.title) for n in a] == [(n.node_id, n.title) for n in b]
    assert a[0].node_id == f"{DOC}:regions:0000"
    assert all(n.depth == 1 or n.parent_id is not None for n in a)
    ids = [n.node_id for n in a]
    assert ids == sorted(ids)


def test_medium_weight_font_counts_as_bold_for_notes():
    first = region(5, 1, "1.\nGeneral", bold=False)
    first["font"]["name"] = "Roboto-Medium"
    regs = contents_page() + [first, region(6, 1, "2.\nBasis"), region(7, 1, "3.\nIncome"),
                              region(7, 2, "4.\nTax", y=400), region(8, 1, "5.\nCapital")]
    nodes = flatten(build_annual_report_tree(view(pages(), regs), RULES), DOC)
    assert [n.title for n in nodes if n.origin == "note"][0] == "1. General"


def _titles(regs):
    return [n.title for n in flatten(build_annual_report_tree(view(pages(), contents_page() + regs), RULES), DOC)]


BODY_TEXT = [region(3, 90 + i, "Body text of the section.", "text", 9, False, y=600) for i in range(3)]
BODY = BODY_TEXT + \
    [region(3, 80, "Retail Banking", size=13, y=60), region(3, 81, "Wealth Management", size=13, y=700)]


def _kept_and_dropped(extra, dropped):
    titles = _titles(BODY + extra)
    assert "Retail Banking" in titles and "Wealth Management" in titles   # genuine headings stay
    assert dropped not in titles


def test_callout_fragment_dropped():
    _kept_and_dropped([region(3, 1, "More than", size=13, y=109)], "More than")


def test_table_caption_dropped():
    _kept_and_dropped([region(3, 1, "Table 2: Three Lines of Defence", size=9, y=156)],
                      "Table 2: Three Lines of Defence")


def test_heading_inside_a_table_dropped():
    table = region(3, 2, None, "table", 9, False, y=180, w=400, h=200)
    head = region(3, 3, "IRB Models and Portfolios", size=9, y=207, x=60, w=150)
    _kept_and_dropped([table, head], "IRB Models and Portfolios")


def test_heading_smaller_than_body_text_dropped():
    _kept_and_dropped([region(3, 1, "Great Eastern Holdings Limited", size=7, y=278)],
                      "Great Eastern Holdings Limited")


def test_section_extends_onto_a_page_whose_body_text_precedes_the_next_heading():
    regs = BODY_TEXT + [region(3, 1, "External Audit", size=10, y=96),
                   region(4, 1, "continuing text in the left column", "text", 9, False, y=96, x=51),
                   region(4, 2, "Internal Audit", size=10, y=96, x=300)]
    nodes = flatten(build_annual_report_tree(view(pages(), contents_page() + regs), RULES), DOC)
    ext = next(n for n in nodes if n.title == "External Audit")
    assert (ext.page_start, ext.page_end) == (3, 4)


def test_subnote_extends_to_its_continued_heading():
    regs = [region(5, 1, "1.\nGeneral"), region(5, 2, "1.1\nScope", size=10, y=500),
            region(6, 1, "1.2\nBasis", size=10, y=96, x=51), region(6, 2, "1.1\nScope (continued)", size=10, y=128, x=300),
            region(7, 1, "2.\nBasis"), region(7, 2, "3.\nIncome", y=400), region(8, 1, "4.\nTax"), region(8, 2, "5.\nCapital", y=400)]
    nodes = flatten(build_annual_report_tree(view(pages(), contents_page() + regs), RULES), DOC)
    scope = next(n for n in nodes if n.title == "1.1 Scope")
    assert (scope.page_start, scope.page_end) == (5, 6)


def test_no_page_labels_falls_back_to_generic_tree_with_gaps():
    unlabeled = pages()
    for p in unlabeled:
        p["page_label"] = None
    regs = contents_page() + [region(3, 1, "Business Review", size=20, bold=False), region(5, 1, "1.\nGeneral")]
    notes: list = []
    nodes = flatten(build_annual_report_tree(view(unlabeled, regs), RULES, notes), DOC)
    assert not any(n.origin.startswith("toc") for n in nodes)          # no skeleton from unresolvable page numbers
    assert "Business Review" in [n.title for n in nodes]
    assert {"page_label_unreliable", "tree_fallback_generic"} <= {g["code"] for g in notes}


def test_missing_font_colour_is_noted():
    notes: list = []
    build_annual_report_tree(view(pages(), contents_page()), RULES, notes)
    assert any(g["code"] == "font_colour_unavailable" for g in notes)


def test_running_header_text_does_not_extend_the_previous_note():
    header = [region(p, 0, "For the financial year ended 31 December 2025", "text", 9, False, y=62) for p in (5, 6, 7, 8)]
    regs = header + [region(5, 1, "1.\nGeneral"), region(6, 1, "2.\nBasis", y=99), region(7, 1, "3.\nIncome"),
                     region(7, 2, "4.\nTax", y=400), region(8, 1, "5.\nCapital")]
    nodes = flatten(build_annual_report_tree(view(pages(), contents_page() + regs), RULES), DOC)
    general = next(n for n in nodes if n.title == "1. General")
    assert (general.page_start, general.page_end) == (5, 5)


def _parents(regs):
    # a second genuine heading keeps the section from collapsing a lone child (that rule is tested elsewhere)
    regs = regs + [region(3, 89, "Closing Remarks", size=13, y=760)]
    nodes = flatten(build_annual_report_tree(view(pages(), contents_page() + BODY_TEXT + regs), RULES), DOC)
    by_id = {n.node_id: n for n in nodes}
    return {n.title: (by_id[n.parent_id].title if n.parent_id else None) for n in nodes}


def test_bullet_heading_nests_under_the_preceding_same_size_heading():
    t = lambda order, y: region(3, order, "Paragraph text.", "text", 9, False, y=y)  # noqa: E731
    p = _parents([region(3, 10, "Board Approval", size=9, y=300), t(11, 312),
                  region(3, 12, "Board Committees", size=9, y=400), t(13, 412),
                  region(3, 14, "• Audit Committee", size=9, y=450), t(15, 462),
                  region(3, 16, "• Ethics Committee", size=9, y=500), t(17, 512),
                  region(3, 18, "Board Access", size=9, y=550), t(19, 562)])
    assert p["• Audit Committee"] == p["• Ethics Committee"] == "Board Committees"
    assert p["Board Committees"] == p["Board Approval"] == p["Board Access"]


def test_same_size_heading_group_nests_under_its_group_head():
    regs = [region(3, 10, "Southeast Asia", size=10, y=100), region(3, 11, "Singapore", size=10, y=118),
            region(3, 12, "OCBC Bank Limited", "text", 7, False, y=138),
            region(3, 13, "Brunei", size=10, x=140, y=118), region(3, 14, "Address line", "text", 7, False, x=140, y=150),
            region(3, 15, "Indonesia", size=10, x=140, y=302),
            region(3, 20, "Greater China", size=10, x=300, y=100), region(3, 21, "Hong Kong SAR", size=10, x=300, y=118)]
    p = _parents(regs)
    assert p["Singapore"] == p["Brunei"] == p["Indonesia"] == "Southeast Asia"
    assert p["Hong Kong SAR"] == "Greater China"
    assert p["Greater China"] == p["Southeast Asia"]


# ---------- rule round 2 (step-2 tree eval, seed 103) ----------

def test_figure_dominant_titles_dropped():
    zh_figure = "400" + chr(0x4e07)                       # "400 wan": a stat callout figure
    p = _parents([region(3, 10, "33% CAGR", size=13, y=300), region(3, 11, zh_figure, size=13, y=350),
                  region(3, 12, ">45%", size=13, y=400), region(3, 13, "Board Matters", size=13, y=450)])
    assert "Board Matters" in p and not {"33% CAGR", zh_figure, ">45%"} & set(p)


def test_headings_inside_chart_or_diagram_boxes_dropped():
    chart = region(3, 9, None, "chart", 9, False, y=280, w=400, h=200)
    p = _parents([chart, region(3, 10, "Senior Management", size=10, y=300, x=80), region(3, 11, "Board Matters", size=13, y=600)])
    assert "Senior Management" not in p and "Board Matters" in p


def test_salutations_and_field_lines_dropped():
    p = _parents([region(3, 10, "Dear Fellow Shareholders,", size=16, y=100), region(3, 11, "Appointed: 20 September 2017",
                  size=10, y=300), region(3, 12, "Principle 1: The Board", size=10, y=400)])
    assert "Dear Fellow Shareholders," not in p and "Appointed: 20 September 2017" not in p
    assert "Principle 1: The Board" in p


def test_subtitle_line_under_a_heading_dropped():
    p = _parents([region(3, 10, "Ms Helen Wong", size=13, y=100, h=14), region(3, 11, "Group Chief Executive Officer",
                  size=10, y=116), region(3, 12, "Biography text.", "text", 9, False, y=140)])
    assert "Ms Helen Wong" in p and "Group Chief Executive Officer" not in p


def test_subheading_set_close_to_its_own_text_is_kept():
    # a first subsection directly under its section heading: its text follows closer than the gap above it
    p = _parents([region(3, 10, "Board Matters", size=13, y=266, h=12), region(3, 11, "Principle 1: The Board",
                  size=10, y=283, h=9), region(3, 12, "The Board is elected.", "text", 9, False, y=295)])
    assert "Principle 1: The Board" in p


def test_subheading_with_about_equal_gaps_is_kept():
    # 2024 en p117: 3.78 pt above, 3.96 pt below; a job title sits clearly apart (5 pt above, 14 pt below)
    p = _parents([region(3, 10, "Report on the Audit", size=10, y=99, h=9.22), region(3, 11, "Our Opinion",
                  size=9, y=112, h=8.04), region(3, 12, "In our opinion, the statements.", "text", 9, False, y=124)])
    assert "Our Opinion" in p


def test_subheading_followed_by_a_table_is_kept():
    p = _parents([region(3, 10, "Net Interest Income", size=13, y=99, h=12), region(3, 11, "Average Balance Sheet",
                  size=10, y=116, h=9), region(3, 12, "2024 2023 Average Balance", "table", 9, False, y=135, h=200)])
    assert "Average Balance Sheet" in p


def test_continued_heading_does_not_duplicate_an_existing_node():
    regs = [region(3, 10, "Overview", size=13, y=100), region(3, 11, "Body.", "text", 9, False, y=130),
            region(4, 10, "Overview (continued)", size=13, y=100), region(4, 11, "Funding", size=10, y=300)]
    nodes = flatten(build_annual_report_tree(view(pages(), contents_page() + regs), RULES), DOC)
    assert [n.title for n in nodes].count("Overview") == 1


def test_group_head_needs_the_next_heading_directly_below_in_its_column():
    regs = [region(3, 10, "Mangrove Programme", size=10, y=100, x=51), region(3, 11, "Malaysia", size=10, y=300, x=225),
            region(3, 12, "Coral reef", size=9, y=320, x=225), region(3, 13, "Indonesia", size=10, y=420, x=225)]
    p = _parents(regs)
    assert p["Malaysia"] == p["Mangrove Programme"]


# --- round 2 W1: headings inside notes, numbering depth, lettered items, "(continued)" repeats ---

NOTES = [region(5, 1, "1.\nGeneral"), region(5, 2, "1.1\nScope", size=10, y=200),
         region(5, 3, "1.2\nBasis of preparation", size=10, y=300), region(6, 1, "2.\nBasis"),
         region(7, 1, "3.\nIncome"), region(7, 6, "4.\nTax", y=400), region(8, 1, "5.\nCapital")]


def _tree(regs):
    return flatten(build_annual_report_tree(view(pages(), contents_page() + regs), RULES), DOC)


def _parent_of(nodes, title):
    by_id = {n.node_id: n for n in nodes}
    n = next(n for n in nodes if n.title == title)
    return by_id[n.parent_id].title if n.parent_id else None


def test_an_unnumbered_heading_inside_a_note_becomes_its_child():
    nodes = _tree(NOTES + [region(7, 5, "Interest Income", size=9, y=200)])
    assert _parent_of(nodes, "Interest Income") == "3. Income"


def test_deeper_numbered_and_lettered_headings_nest_inside_a_subnote():
    regs = NOTES + [region(5, 4, "1.2.1 Statement of compliance", size=10, y=330),
                    region(5, 5, "1.2.1.1 Standards adopted", size=10, y=360),
                    region(5, 6, "(a) Equity price risk", size=10, y=390),
                    region(5, 7, "1.2.2 Going concern", size=10, y=420)]
    nodes = _tree(regs)
    assert _parent_of(nodes, "1.2.1 Statement of compliance") == "1.2 Basis of preparation"
    assert _parent_of(nodes, "1.2.1.1 Standards adopted") == "1.2.1 Statement of compliance"
    assert _parent_of(nodes, "(a) Equity price risk") == "1.2.1.1 Standards adopted"
    assert _parent_of(nodes, "1.2.2 Going concern") == "1.2 Basis of preparation"


def test_a_continued_repeat_in_another_size_is_not_a_new_node():
    regs = [region(3, 10, "Overview", size=13, bold=True, y=100), region(3, 11, "Body.", "text", 9, False, y=130),
            region(4, 10, "Overview (continued)", size=12, bold=False, y=100),
            region(4, 11, "Funding", size=10, y=300)]
    nodes = _tree(regs)
    assert [n.title for n in nodes].count("Overview") == 1
    assert _parent_of(nodes, "Funding") == "Overview"


def test_a_heading_over_a_big_figure_is_a_stat_callout():
    _kept_and_dropped([region(3, 20, "Delivering Shareholder Returns", size=13, y=111, x=60),
                       region(3, 21, "60%", "text", 26, False, y=144, x=103, w=50, h=23)],
                      "Delivering Shareholder Returns")


def test_a_heading_carrying_a_figure_with_a_unit_is_a_stat_callout():
    _kept_and_dropped([region(3, 20, "Resilient Net Profit $7.42 billion 2%", size=13, y=267, x=399)],
                      "Resilient Net Profit $7.42 billion 2%")
    _kept_and_dropped([region(3, 20, "总派息率60%", size=13, y=267, x=399)], "总派息率60%")


def test_a_name_after_a_signature_is_not_a_heading():
    _kept_and_dropped([region(3, 20, "", "signature", None, False, y=97, x=226),
                       region(3, 21, "Mr Tan Teck Long", size=9, y=139, x=225),
                       region(3, 22, "Group Chief Executive Officer", "text", 9, False, y=153, x=225)],
                      "Mr Tan Teck Long")


def test_a_row_of_card_labels_is_not_a_heading_group():
    cards = [region(3, 20 + i, t, size=10, y=225, x=45 + 102 * i, w=60)
             for i, t in enumerate(["Lasting Value", "Integrity", "Forward-Looking", "Respect"])]
    titles = _titles(BODY + cards)
    assert "Retail Banking" in titles and not {"Integrity", "Respect"} & set(titles)


def test_three_sections_side_by_side_stay():
    cols = [region(3, 20 + i, t, size=12, y=284, x=43 + 174 * i)
            for i, t in enumerate(["Accelerating the Transition", "Bringing Impact to Communities",
                                   "Conducting Our Business Responsibly"])]
    assert {"Bringing Impact to Communities", "Conducting Our Business Responsibly"} <= set(_titles(BODY + cols))


def test_a_title_starting_with_a_figure_stays():
    assert "$2.5 billion Capital Return" in _titles(BODY + [region(3, 20, "$2.5 billion Capital Return", size=10, y=400)])


def test_two_column_headings_at_the_same_height_stay():
    cols = [region(3, 20, "Funding and Liquidity", size=10, y=400, x=51), region(3, 21, "Capital Position", size=10, y=400, x=312)]
    assert {"Funding and Liquidity", "Capital Position"} <= set(_titles(BODY + cols))


def test_two_character_chinese_country_labels_are_headings():
    regs = [region(3, 10, "马来西亚", size=10, y=100), region(3, 11, "绿色计划", size=9, y=118),
            region(3, 12, "Body.", "text", 9, False, y=130),
            region(3, 13, "中国", size=10, y=300), region(3, 14, "小小绿色夏令营", size=9, y=318),
            region(3, 15, "Body.", "text", 9, False, y=330)]
    p = _parents(regs)
    assert p["小小绿色夏令营"] == "中国"


def test_generic_and_single_character_labels_stay_junk():
    titles = _titles(BODY + [region(3, 20, "集团", size=10, y=400), region(3, 21, "表", size=10, y=450)])
    assert "集团" not in titles and "表" not in titles


def test_a_light_continued_repeat_of_a_bold_heading_is_not_its_child():
    regs = [region(3, 10, "Results Overview", size=13, bold=True, y=99), region(3, 11, "Body.", "text", 9, False, y=130),
            region(4, 10, "Results Overview (continued)", size=13, bold=False, y=99),
            region(4, 11, "Dividend", size=10, y=300), region(4, 12, "Body.", "text", 9, False, y=320)]
    nodes = _tree(regs)
    assert [n.title for n in nodes].count("Results Overview") == 1
    assert _parent_of(nodes, "Dividend") == "Results Overview"


def test_a_pull_quote_above_the_next_heading_does_not_extend_the_previous_section():
    body = [region(3, 90 + i, "Body text of the section.", "text", 9, False, y=600) for i in range(3)]
    regs = body + [region(3, 10, "Steady Financial Performance", size=10, y=439),
                   region(4, 10, "We will build on the strength of one group.", "text", 16, False, y=57),
                   region(4, 11, "Sustainable Shareholder Returns", size=10, y=203),
                   region(4, 12, "Body text.", "text", 9, False, y=220)]
    nodes = _tree(regs)
    steady = next(n for n in nodes if n.title == "Steady Financial Performance")
    assert (steady.page_start, steady.page_end) == (3, 3)


def test_a_heading_between_two_subnotes_gets_a_valid_range_between_them():
    regs = [region(5, 1, "1.\nGeneral"), region(5, 2, "1.1\nScope", size=10, y=200),
            region(6, 1, "Transition Notes", size=9, y=50), region(6, 2, "Body.", "text", 9, False, y=70),
            region(6, 3, "1.2\nBasis of preparation", size=10, y=300),
            region(7, 1, "2.\nBasis"), region(8, 1, "3.\nIncome"), region(8, 2, "4.\nTax", y=400),
            region(8, 3, "5.\nCapital", y=600)]
    nodes = _tree(regs)
    extra = next(n for n in nodes if n.title == "Transition Notes")
    assert extra.page_start <= extra.page_end
    assert all(n.page_start <= n.page_end for n in nodes)
    assert _parent_of(nodes, "Transition Notes") in ("1. General", "1.1 Scope")


def test_host_choice_follows_reading_order_across_columns():
    # note 2 starts low in the left column; its subnote 2.2 sits higher, in the right column, later in reading order
    regs = [region(5, 1, "1.\nGeneral", y=100), region(5, 10, "2.\nPolicies", y=345, x=51),
            region(5, 11, "2.1\nBasis of preparation", size=10, y=377, x=51),
            region(5, 12, "2.2\nBasis of consolidation", size=10, y=283, x=312),
            region(6, 1, "2.2.1 Subsidiaries", size=9, y=50), region(6, 2, "Body.", "text", 9, False, y=70),
            region(7, 1, "3.\nIncome"), region(8, 1, "4.\nTax"), region(8, 2, "5.\nCapital", y=400)]
    nodes = _tree(regs)
    assert _parent_of(nodes, "2.2.1 Subsidiaries") == "2.2 Basis of consolidation"
    assert all(n.page_start <= n.page_end for n in nodes)


def test_a_title_wrapped_over_two_heading_regions_is_one_title():
    regs = [region(3, 10, "Overview", size=13, y=60), region(3, 11, "Body.", "text", 9, False, y=80),
            region(4, 10, "Pursuing Sustainable", size=13, x=51, y=99, h=12),
            region(4, 11, "Growth", size=13, x=85, y=114, h=12),
            region(4, 12, "Body text.", "text", 9, False, y=140)]
    titles = _titles(regs)
    assert "Pursuing Sustainable Growth" in titles and "Growth" not in titles


def test_a_group_head_and_its_first_member_are_not_merged():
    regs = [region(3, 10, "Southeast Asia", size=10, y=100, h=10), region(3, 11, "Singapore", size=10, y=118, h=10),
            region(3, 12, "OCBC Bank Limited", "text", 7, False, y=138)]
    titles = _titles(regs)
    assert "Southeast Asia" in titles and "Singapore" in titles


def test_a_numbered_second_line_is_not_merged():
    regs = [region(3, 10, "Basis of Consolidation", size=10, y=100, h=10),
            region(3, 11, "2.2.1 Subsidiaries", size=10, y=112, h=10), region(3, 12, "Body.", "text", 9, False, y=130)]
    assert "2.2.1 Subsidiaries" in _titles(regs)


def test_a_numbered_heading_repeated_without_continued_keeps_its_first_copy():
    regs = NOTES + [region(5, 4, "1.2.1 Measurement", size=9, y=330), region(5, 5, "Body.", "text", 9, False, y=345),
                    region(5, 6, "1.2.1 Measurement", size=9, y=500, x=312)]
    nodes = _tree(regs)
    assert [n.title for n in nodes].count("1.2.1 Measurement") == 1


def test_dotted_headings_nest_under_their_number_prefix():
    regs = NOTES + [region(5, 4, "1.2.5 Contract Boundary", size=9, y=330),
                    region(5, 5, "1.2.6 Measurement", size=10, y=360),
                    region(5, 6, "1.2.6.6 Acquisition Cash Flows", size=10, y=390),
                    region(5, 7, "Body.", "text", 9, False, y=420)]
    nodes = _tree(regs)
    assert _parent_of(nodes, "1.2.6.6 Acquisition Cash Flows") == "1.2.6 Measurement"
    assert _parent_of(nodes, "1.2.6 Measurement") == "1.2 Basis of preparation"


def test_a_dotted_heading_goes_to_the_subnote_its_number_names():
    # 1.1.5 sits on a page that, by position, falls inside subnote 1.2's range
    regs = [region(5, 1, "1.\nGeneral"), region(5, 2, "1.1\nScope", size=10, y=200),
            region(5, 3, "1.2\nBasis of preparation", size=10, y=300),
            region(5, 4, "1.1.5 Regulatory Requirement", size=9, y=320), region(5, 5, "Body.", "text", 9, False, y=340),
            region(6, 1, "2.\nBasis"), region(7, 1, "3.\nIncome"), region(7, 6, "4.\nTax", y=400),
            region(8, 1, "5.\nCapital")]
    assert _parent_of(_tree(regs), "1.1.5 Regulatory Requirement") == "1.1 Scope"


def test_an_unnumbered_heading_after_a_dotted_one_nests_under_it_but_a_roman_group_does_not():
    regs = NOTES + [region(5, 4, "(I) Financial Assets", size=9, y=320),
                    region(5, 5, "1.2.1 As Lessee", size=9, y=340),
                    region(5, 6, "Right-of-Use Assets", size=9, y=360),
                    region(5, 7, "(II) Other Assets", size=9, y=380),
                    region(5, 8, "Body.", "text", 9, False, y=400)]
    nodes = _tree(regs)
    assert _parent_of(nodes, "Right-of-Use Assets") == "1.2.1 As Lessee"
    assert _parent_of(nodes, "(II) Other Assets") == _parent_of(nodes, "(I) Financial Assets")


# --- round 2 W1, bounded round 5 ---

def test_a_continued_running_header_does_not_extend_the_previous_section():
    regs = [region(3, 10, "Operational Risk", size=10, y=400), region(3, 11, "Body text.", "text", 9, False, y=420),
            region(4, 10, "38.3 Market Risk (continued)", "text", 9, False, y=40),
            region(4, 11, "Hedging", size=10, y=60), region(4, 12, "Body text.", "text", 9, False, y=80)]
    nodes = _tree(regs)
    op = next(n for n in nodes if n.title == "Operational Risk")
    assert (op.page_start, op.page_end) == (3, 3)


def test_a_dotted_heading_never_nests_under_a_dotted_sibling():
    regs = NOTES + [region(5, 4, "1.2.6.4 Subsequent Measurement", size=10, y=330),
                    region(5, 5, "Onerous contracts", size=9, y=345),
                    region(5, 6, "1.2.6.5 Reinsurance Contracts", size=9, y=360),
                    region(5, 7, "Body.", "text", 9, False, y=380)]
    nodes = _tree(regs)
    assert _parent_of(nodes, "1.2.6.5 Reinsurance Contracts") == _parent_of(nodes, "1.2.6.4 Subsequent Measurement")


def test_a_continued_line_is_a_complete_title_and_is_not_merged():
    regs = [region(3, 10, "Overview", size=13, y=60), region(3, 11, "Body.", "text", 9, False, y=80),
            region(4, 10, "Financial Assets (continued)", size=10, x=51, y=99, h=10),
            region(4, 11, "Classification and Measurement", size=10, x=51, y=112, h=10),
            region(4, 12, "Body text.", "text", 9, False, y=140)]
    assert "Classification and Measurement" in _titles(regs)



# --- review of PR #13 ---

def test_a_dotted_heading_outside_the_notes_keeps_its_own_section():
    regs = NOTES + [region(3, 10, "1.2.3 Our Targets", size=10, y=300), region(3, 11, "Body.", "text", 9, False, y=320),
                    region(4, 10, "Highlights", size=10, y=100), region(4, 11, "Body.", "text", 9, False, y=120)]
    nodes = _tree(regs)
    t = next(n for n in nodes if n.title == "1.2.3 Our Targets")
    assert _parent_of(nodes, "1.2.3 Our Targets") == "Overview" and (t.page_start, t.page_end) == (3, 3)


def test_moving_a_dotted_heading_up_moves_the_headings_after_it_too_and_keeps_ranges_valid():
    regs = NOTES + [region(5, 4, "1.2.6.4 Subsequent Measurement", size=10, y=330),
                    region(5, 5, "1.2.6.5 Reinsurance Contracts", size=9, y=360),
                    region(5, 6, "Later Topic", size=9.5, y=380), region(5, 7, "Body.", "text", 9, False, y=400)]
    nodes = _tree(regs)
    assert _parent_of(nodes, "1.2.6.5 Reinsurance Contracts") == _parent_of(nodes, "1.2.6.4 Subsequent Measurement")
    assert all(n.page_start <= n.page_end for n in nodes)
    by = {n.node_id: n for n in nodes}
    assert all(by[n.parent_id].page_start <= n.page_start and n.page_end <= by[n.parent_id].page_end
               for n in nodes if n.parent_id)


def test_four_column_section_headings_with_running_text_are_kept():
    cols = [region(3, 20 + i, t, size=10, y=225, x=37 + 130 * i, w=110)
            for i, t in enumerate(["Environment", "Social", "Governance", "Economic"])]
    texts = [region(3, 30 + i, "Long body text paragraph describing the section in detail.", "text", 9, False,
                    y=245, x=37 + 130 * i, w=110) for i in range(4)]
    assert {"Environment", "Governance"} <= set(_titles(BODY + cols + texts))


def test_a_dotted_heading_moves_up_until_its_parent_is_a_number_prefix():
    regs = NOTES + [region(5, 4, "1.2.6 Measurement", size=10, y=330), region(5, 5, "1.2.6.4 Subsequent", size=9.5, y=350),
                    region(5, 6, "1.2.9.1 Other Matters", size=9, y=370), region(5, 7, "Body.", "text", 9, False, y=400)]
    nodes = _tree(regs)
    assert _parent_of(nodes, "1.2.9.1 Other Matters") == "1.2 Basis of preparation"
