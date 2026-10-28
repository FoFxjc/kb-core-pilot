from decimal import Decimal

from kb_core.build.cells import load_units
from kb_core.build.tables import interpret, merge_continued

U = load_units("banking")


def cell(r, c, text, header=False, x0=None, rs=1, cs=1):
    x0 = 72.0 + 150 * c if x0 is None else x0
    return {"r": r, "c": c, "rs": rs, "cs": cs, "text": text, "bbox": [x0, 300 + 14 * r, x0 + 60, 310 + 14 * r],
            "bbox_source": "text", "is_header": header}


def table(cells, tid="d:t0001_01", hint=None, n_rows=None, n_cols=None):
    return {"table_id": tid, "page_no": 1, "cells": cells, "n_rows": n_rows or 1 + max(c["r"] for c in cells),
            "n_cols": n_cols or 1 + max(c["c"] for c in cells), "continued_hint": hint, "markdown": ""}


def test_header_rows_joined_across_spans():
    t = table([cell(0, 1, "Group", True, cs=2), cell(1, 1, "2025", True), cell(1, 2, "2024", True),
               cell(2, 0, "Net profit"), cell(2, 1, "7,587"), cell(2, 2, "7,589")])
    it = interpret(t, "", U)
    assert it.columns[1:] == ["Group 2025", "Group 2024"]
    assert it.rows[0].label == "Net profit" and [v.num for v in it.rows[0].values] == [Decimal("7587"), Decimal("7589")]


def test_unit_hint_from_header_or_preceding_text():
    t = table([cell(0, 1, "2025", True), cell(1, 0, "Total income"), cell(1, 1, "14,614")])
    assert interpret(t, "Five-year summary ($ million)", U).unit_hint == "$ million"
    t2 = table([cell(0, 1, "2025 $ million", True), cell(1, 0, "Total income"), cell(1, 1, "14,614")])
    assert interpret(t2, "", U).unit_hint == "$ million"


def test_row_path_from_label_indentation():
    t = table([cell(0, 1, "2025", True),
               cell(1, 0, "A", x0=40), cell(1, 1, "1"), cell(2, 0, "B", x0=48), cell(2, 1, "2"),
               cell(3, 0, "C", x0=48), cell(3, 1, "3"), cell(4, 0, "D", x0=40), cell(4, 1, "4")])
    it = interpret(t, "", U)
    assert [r.path for r in it.rows] == [["A"], ["A", "B"], ["A", "C"], ["D"]]
    assert not it.indent_unavailable


def test_row_path_flat_when_bbox_missing():
    cells = [cell(0, 1, "2025", True), cell(1, 0, "A"), cell(1, 1, "1"), cell(2, 0, "B"), cell(2, 1, "2")]
    cells[3]["bbox"] = None
    it = interpret(table(cells), "", U)
    assert [r.path for r in it.rows] == [["A"], ["B"]] and it.indent_unavailable


def test_table_without_numbers_is_an_artifact():
    t = table([cell(0, 0, "Some heading"), cell(1, 0, "A paragraph wrongly detected as a table")])
    assert interpret(t, "", U).is_artifact


def test_merge_continued_heading():
    a, b, c = (table([cell(0, 0, "x")], tid=f"d:t000{i}_01") for i in (1, 2, 3))
    b["continued_hint"] = {"table_id": a["table_id"], "reason": "continued_heading"}
    c["continued_hint"] = {"table_id": b["table_id"], "reason": "continued_heading"}
    [m] = merge_continued([a, b, c])
    assert m.part_table_ids == ["d:t0001_01", "d:t0002_01", "d:t0003_01"] and m.decision == "merged"
    assert m.reason == "continued_heading"


def test_same_first_row_is_hint_only():
    a, b = (table([cell(0, 0, "x")], tid=f"d:t000{i}_01") for i in (1, 2))
    b["continued_hint"] = {"table_id": a["table_id"], "reason": "same_first_row"}
    [m] = merge_continued([a, b])
    assert m.decision == "hint" and m.part_table_ids == ["d:t0001_01", "d:t0002_01"]
