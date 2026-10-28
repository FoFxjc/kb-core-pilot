"""Contents pages and printed page numbers (port of kb profiles/annual_report/tree.py toc_items / page_mapper).

kb read PyMuPDF lines; kb-core rebuilds the same lines from intake regions: a one-line region is one line, a
multi-line region is split into lines with the layout words inside its box. Bold and size come from the region font.
"""

import re
from dataclasses import dataclass

from kb_core.build.view import DocView

LINE_TYPES = ("text", "heading", "title", "toc", "list", "caption", "table")  # kb read every text line


@dataclass
class Line:
    x: float
    y: float
    text: str
    bold: bool | None    # None: the line comes from a multi-line region, whose one font says nothing per line
    size: float
    col: int


@dataclass
class TocItem:
    kind: str            # header | entry
    title: str
    printed: str | None  # printed page number, "ibc" for the inside back cover, None for headers
    bold: bool
    y: float


NUMBER_WORD = re.compile(r"^(\d{1,3}|IBC)$")


def _split_by_words(region: dict, words: list[list], gap: float = 20.0,
                    number_gap: float = 8.0) -> list[tuple[float, float, str]]:
    """Lines of a multi-line region from the layout words in its box; a run breaks at a wide gap, or before a
    page-number word at a smaller one (long titles run close to their page number)."""
    x0, y0, x1, y1 = region["bbox"]
    inside = sorted((w for w in words if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1),
                    key=lambda w: (round(w[1]), w[0]))  # by word centre: words overhang region boxes slightly
    rows: list[list[list]] = []
    for w in inside:
        if rows and abs(rows[-1][0][1] - w[1]) <= 2:
            rows[-1].append(w)
        else:
            rows.append([w])
    out = []
    for row in rows:
        row.sort(key=lambda w: w[0])
        run = [row[0]]
        for w in row[1:]:
            dx = w[0] - run[-1][2]
            if dx > gap or (dx > number_gap and NUMBER_WORD.match(w[4])):
                out.append((run[0][0], run[0][1], " ".join(x[4] for x in run)))
                run = [w]
            else:
                run.append(w)
        out.append((run[0][0], run[0][1], " ".join(x[4] for x in run)))
    return out


def page_lines(view: DocView, page_no: int, size_range: tuple[float, float] | None = None) -> list[Line]:
    width = view.page(page_no)["width"]
    lines = []
    for r in view.regions:
        if r["page_no"] != page_no or r["layer"] != "body" or r["type"] not in LINE_TYPES or not (r["text"] or "").strip():
            continue
        font = r["font"] or {}
        size, bold = float(font.get("size") or 0), bool(font.get("bold"))
        if size_range and not size_range[0] <= size <= size_range[1]:
            continue
        text = r["text"].strip()
        parts = [(r["bbox"][0], r["bbox"][1], text)] if "\n" not in text else _split_by_words(r, view.words(page_no))
        for x, y, t in parts:
            lines.append(Line(x, y, t.strip(), bold if len(parts) == 1 else None, size, 0 if x < width / 2 else 1))
    return lines


def parse_toc(lines: list[Line], rules: dict) -> list[TocItem]:
    """Contents items in reading order: entries (title + printed page), group headers (bold, no page)."""
    num = re.compile(rules.get("number", r"^\d{1,3}$"))
    ibc = re.compile(rules.get("inside_back_cover", r"^(IBC|Inside Back Cover)$"), re.I)
    items: list[TocItem] = []
    for col in (0, 1):
        cl = [ln for ln in lines if ln.col == col]
        if not cl:
            continue
        x0 = min(ln.x for ln in cl)
        titles = sorted((ln for ln in cl if ln.x < x0 + 5 and not num.match(ln.text)), key=lambda ln: ln.y)
        nums = [ln for ln in cl if ln.x > x0 + rules["number_dx"] and (num.match(ln.text) or ibc.match(ln.text))]
        prev: TocItem | None = None
        for ln in titles:
            n = next((m for m in nums if abs(m.y - ln.y) <= rules["same_line_dy"]), None)
            if n:
                prev = TocItem("entry", ln.text, "ibc" if ibc.match(n.text) else n.text, bool(ln.bold), ln.y)
                items.append(prev)
            elif prev and ln.y - prev.y < rules["continuation_dy"] and bool(ln.bold) == prev.bold:
                prev.title += ("" if re.search(r"[\u4e00-\u9fff]$", prev.title) else " ") + ln.text
                prev.y = ln.y
            elif ln.bold or (ln.bold is None and (prev is None or ln.y - prev.y >= rules["continuation_dy"])):
                prev = TocItem("header", ln.text, None, True, ln.y)
                items.append(prev)
            else:
                prev = None
    return items


def printed_to_physical(pages: list[dict]) -> tuple[dict[str, int], bool]:
    """Printed page label -> first physical page carrying it (intake's page_label). reliable is False when the
    package has no page labels at all (page numbers in contents cannot be resolved)."""
    mapping: dict[str, int] = {}
    for p in pages:
        label = p.get("page_label")
        if label:
            mapping.setdefault(str(label), p["page_no"])
    return mapping, bool(mapping)
