from kb_core.build.toc import page_lines, parse_toc, printed_to_physical
from tests.tree_helpers import page, region, view


def toc_regions():
    r = [region(3, 1, "Overview", "text", 9, True, y=283),
         region(3, 2, "Financial Highlights", "text", 9, False, y=295),
         region(3, 3, "2", "text", 9, False, x=281, y=295, w=5),
         region(3, 4, "Our Chairman's Take on Positioning OCBC", "text", 9, True, y=345),
         region(3, 5, "for the Future", "text", 9, True, y=357),
         region(3, 6, "6", "text", 9, False, x=281, y=345, w=5),
         region(3, 7, "Creating Value", "text", 9, False, y=308),
         region(3, 8, "3", "text", 9, False, x=281, y=308, w=5)]
    return r


def test_toc_entries_and_groups():
    v = view([page(n) for n in range(1, 8)], toc_regions())
    items = parse_toc(page_lines(v, 3, (8, 10.5)), {"number_dx": 150, "same_line_dy": 2.5, "continuation_dy": 14})
    assert [(i.kind, i.title, i.printed) for i in items] == [
        ("header", "Overview", None),
        ("entry", "Financial Highlights", "2"),
        ("entry", "Creating Value", "3"),
        ("entry", "Our Chairman's Take on Positioning OCBC for the Future", "6"),
    ]
    assert items[3].bold and not items[1].bold


def test_multi_line_toc_region_split_by_words():
    r = region(3, 1, "Chin Yee, CFO\n32\nNoel, CRO\n36", "toc", 9, False, x=322, y=287, w=237, h=40)
    words = {3: [[323, 288, 380, 296, "Chin"], [382, 288, 400, 296, "Yee,"], [402, 288, 420, 296, "CFO"],
                 [548, 288, 556, 296, "32"], [323, 300, 350, 308, "Noel,"], [352, 300, 370, 308, "CRO"],
                 [548, 300, 556, 308, "36"]]}
    v = view([page(3)], [r], words)
    lines = page_lines(v, 3, (8, 10.5))
    assert [(round(ln.x), ln.text) for ln in lines] == [(323, "Chin Yee, CFO"), (548, "32"), (323, "Noel, CRO"),
                                                       (548, "36")]


def test_printed_to_physical_from_labels():
    pages = [page(1, ""), page(2, ""), page(3, "1"), page(4, "2")]
    pages[0]["page_label"] = None
    pages[1]["page_label"] = None
    mapping, reliable = printed_to_physical(pages)
    assert mapping == {"1": 3, "2": 4} and reliable


def test_printed_to_physical_unreliable_without_labels():
    pages = [page(1), page(2)]
    for p in pages:
        p["page_label"] = None
    mapping, reliable = printed_to_physical(pages)
    assert mapping == {} and not reliable


def test_multi_line_toc_region_groups_and_trailing_numbers():
    """Inside one toc region every line has the region's (non-bold) font: a numberless line after a gap is a group
    header; a page number close to a long title is still split off."""
    r = region(3, 1, "lines\nof a contents block", "toc", 9, False, x=322, y=378, w=237, h=80)
    words = {3: [[323, 379, 380, 387, "Hwee"], [382, 379, 400, 387, "Boon"], [549, 379, 556, 387, "46"],
                 [323, 404, 380, 412, "Governance"],
                 [323, 416, 380, 424, "Corporate"], [382, 416, 430, 424, "Governance"], [549, 416, 556, 424, "48"],
                 [323, 429, 400, 437, "Seeking"], [402, 429, 535, 437, "Re-Election"], [545, 429, 553, 437, "68"]]}
    items = parse_toc(page_lines(view([page(3)], [r], words), 3, (8, 10.5)),
                      {"number_dx": 150, "same_line_dy": 2.5, "continuation_dy": 14})
    assert [(i.kind, i.title, i.printed) for i in items] == [
        ("entry", "Hwee Boon", "46"), ("header", "Governance", None), ("entry", "Corporate Governance", "48"),
        ("entry", "Seeking Re-Election", "68")]


def test_contents_laid_out_as_a_table_region_is_read():
    r = region(3, 1, "Directors' Statement\n107\nNotes\n128", "table", 9, False, x=50, y=280, w=240, h=30)
    words = {3: [[51, 281, 120, 289, "Directors'"], [122, 281, 170, 289, "Statement"], [270, 281, 284, 289, "107"],
                 [51, 293, 90, 301, "Notes"], [270, 293, 284, 301, "128"]]}
    items = parse_toc(page_lines(view([page(3)], [r], words), 3, (8, 10.5)),
                      {"number_dx": 150, "same_line_dy": 2.5, "continuation_dy": 14})
    assert [(i.title, i.printed) for i in items] == [("Directors' Statement", "107"), ("Notes", "128")]


def test_words_overhanging_the_region_box_still_count():
    r = region(3, 1, "a\nb", "toc", 9, False, x=36, y=361, w=236, h=107)   # box 361..468
    words = {3: [[37, 360, 70, 369, "Directors"], [262, 359, 270, 368, "55"],
                 [37, 459, 90, 470, "Notes"], [262, 459, 270, 470, "76"]]}
    lines = page_lines(view([page(3)], [r], words), 3, (8, 10.5))
    assert [ln.text for ln in lines] == ["Directors", "55", "Notes", "76"]
