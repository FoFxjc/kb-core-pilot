"""Table-of-contents tree from intake regions (design §3.1; port of kb profiles/annual_report/tree.py).

Annual report: a skeleton from the contents page (groups and entries, printed pages resolved to physical pages,
divider and sub-contents pages moved to the section that follows), notes split by their numbered headings
(N. / N.M, consecutive), and the heading regions inside each section attached under the deepest skeleton node,
nested by font size. kb attached PageIndex Flash nodes here; kb-core uses intake's heading regions instead.
Generic: heading regions only, nested by font size.

Every threshold and pattern comes from profiles/<doc_type>/tree.yaml.
"""

import re
from collections import Counter
from dataclasses import dataclass, field, replace

from kb_core.build.toc import page_lines, parse_toc, printed_to_physical
from kb_core.build.view import DocView

CJK_END = re.compile(r"[\u4e00-\u9fff]$")


@dataclass(frozen=True)
class Layout:
    """Layout thresholds and patterns of a profile (tree.yaml `headings` / `notes`; fallbacks for profiles without
    them)."""
    dotted: re.Pattern
    roman: re.Pattern
    continued: re.Pattern
    row_dy: float
    card_row: int
    card_max_pitch: float
    wrap_gap: float
    display_factor: float


def layout(rules: dict) -> Layout:
    hr, nr = rules.get("headings") or {}, rules.get("notes") or {}
    return Layout(dotted=re.compile(nr.get("dotted", r"^(\d{1,2}(?:\.\d{1,2}){2,})\s")),
                  roman=re.compile(nr.get("roman_group", r"^\((?:I|II|III|IV|V|VI|VII|VIII|IX|X)\)\s")),
                  continued=re.compile(nr.get("continued", r"[(\uff08]\s*(continued|\u7eed)\s*[)\uff09]"), re.I),
                  row_dy=float(hr.get("row_dy", 2.0)), card_row=int(hr.get("card_row", 4)),
                  card_max_pitch=float(hr.get("card_max_pitch", 115)), wrap_gap=float(hr.get("wrap_gap", 0.5)),
                  display_factor=float(hr.get("display_text_factor", 1.5)))


@dataclass
class Node:
    title: str
    start: int
    end: int
    origin: str
    y: float = 0.0
    size: float = 0.0
    region_ids: list[str] = field(default_factory=list)
    nodes: list["Node"] = field(default_factory=list)
    section_type: str | None = None
    section_rule: str | None = None
    text_before: bool = False   # body text comes before this heading on its page (the previous node continues there)
    order: int = 0              # reading order of the heading region
    x: float = 0.0              # left edge of the heading region


@dataclass
class TreeNode:
    node_id: str
    parent_id: str | None
    depth: int
    ord: int
    title: str
    page_start: int
    page_end: int
    origin: str
    region_ids: list[str]
    is_primary: bool = True
    section_type: str | None = None
    section_rule: str | None = None


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def join_lines(text: str) -> str:
    out = ""
    for part in (p.strip() for p in text.splitlines()):
        if part:
            out += ("" if not out or CJK_END.search(out) else " ") + part
    return out


def body_colour(regions: list[dict]) -> str | None:
    """Most common font colour of text regions; None when the package carries no colours (CR-1)."""
    colours = Counter((r["font"] or {}).get("color") for r in regions if r["type"] == "text" and r["font"])
    colours.pop(None, None)
    return colours.most_common(1)[0][0] if colours else None


def is_bold(font: dict | None, names: list[str]) -> bool:
    font = font or {}
    return bool(font.get("bold")) or any(n in (font.get("name") or "") for n in names)


def _size(r: dict, names: list[str] = ()) -> float:
    f = r["font"] or {}
    return float(f.get("size") or 0) + (0.01 if is_bold(f, names) else 0)


def nav_pages(view: DocView, max_chars: int) -> set[int]:
    return {p["page_no"] for p in view.pages if len(re.sub(r"\s", "", p["text"] or "")) < max_chars}


# ---------- annual report skeleton ----------

def _toc_items(view: DocView, page_no: int, rules: dict):
    return parse_toc(page_lines(view, page_no, tuple(rules["line_size"])), rules)


def _find_toc_page(view: DocView, rules: dict) -> int | None:
    best, best_n = None, 0
    for p in range(1, min(rules["scan_pages"], view.page_count) + 1):
        n = sum(1 for it in _toc_items(view, p, rules) if it.kind == "entry")
        if n >= rules["min_entries"] and n > best_n:
            best, best_n = p, n
    return best


def _sub_toc_pages(view: DocView, toc_page: int, rules: dict) -> list[int]:
    out = []
    for p in view.pages:
        if p["page_no"] == toc_page or len(p["text"] or "") > rules["sub_toc_max_chars"]:
            continue
        nums = [int(it.printed) for it in _toc_items(view, p["page_no"], rules)
                if it.kind == "entry" and it.printed and it.printed.isdigit()]
        if len(nums) >= rules["sub_toc_min_entries"] and all(a < b for a, b in zip(nums, nums[1:])):
            out.append(p["page_no"])
    return out


def _skeleton(view: DocView, rules: dict, toc_page: int, nav: set[int], notes: list) -> list[Node] | None:
    """The contents skeleton, or None when too few entries resolve to physical pages (no usable page labels)."""
    trules = rules["toc"]
    n = view.page_count
    to_phys, reliable = printed_to_physical(view.pages)
    items = _toc_items(view, toc_page, trules)

    def phys(it):
        return n - 1 if it.printed == "ibc" else to_phys.get(it.printed)

    entries = [(it, phys(it)) for it in items if it.kind == "entry" and phys(it)]
    if not reliable:
        notes.append({"code": "page_label_unreliable", "detail": "the package has no printed page labels; "
                      "contents page numbers cannot be resolved to physical pages"})
    if len(entries) < trules["min_entries"]:
        notes.append({"code": "tree_fallback_generic", "page_no": toc_page,
                      "detail": f"only {len(entries)} contents entries resolve to physical pages; "
                                "the tree is built from headings only"})
        return None
    starts = sorted(p for _, p in entries)
    rng = {}
    for it, p in entries:
        nxt = [s for s in starts if s > p]
        rng[id(it)] = [p, (nxt[0] - 1) if nxt else n]
    by_start = sorted(rng.values(), key=lambda r: r[0])
    for prev, nxt in zip(by_start, by_start[1:]):
        while prev[1] > prev[0] and prev[1] in nav and prev[1] == nxt[0] - 1:
            prev[1] -= 1
            nxt[0] -= 1
    top: list[Node] = []
    group: Node | None = None
    for it in items:
        if it.kind == "header":
            group = Node(it.title, 0, 0, "toc_group")
            top.append(group)
        elif id(it) in rng:
            s, e = rng[id(it)]
            node = Node(it.title, s, e, "toc")
            if it.bold:
                group = None
                top.append(node)
            elif group is not None:
                group.nodes.append(node)
            else:
                top.append(node)
    top = [t for t in top if t.origin != "toc_group" or t.nodes]
    for g in top:
        if g.origin == "toc_group":
            g.start, g.end = min(c.start for c in g.nodes), max(c.end for c in g.nodes)
    top.sort(key=lambda t: t.start)
    if top and top[0].start > 1:
        lang = "zh" if items and re.search(r"[\u4e00-\u9fff]", items[0].title) else "en"
        top.insert(0, Node(rules["preface_title"][lang], 1, top[0].start - 1, "toc_preface"))
    leaves = [c for t in top for c in (t.nodes or [t]) if c.origin == "toc"]
    for sub in _sub_toc_pages(view, toc_page, trules):
        subs = [it for it in _toc_items(view, sub, trules) if it.kind == "entry" and it.printed != "ibc"]
        for host in leaves:
            kids = []
            for it in subs:
                p = to_phys.get(it.printed)
                if p and host.start <= p <= host.end and norm(it.title) != norm(host.title) \
                        and not any(norm(it.title) == norm(x.title) for x in leaves):
                    kids.append((it.title, p))
            if len(kids) >= 2 and not host.nodes:
                kids.sort(key=lambda k: k[1])
                for (title, p), nxt in zip(kids, kids[1:] + [None]):
                    end = (nxt[1] - 1) if nxt else host.end
                    host.nodes.append(Node(title, p, max(p, end), "subtoc"))
                if kids[0][1] > host.start:
                    host.nodes.insert(0, Node(host.title + " (intro)", host.start, kids[0][1] - 1, "subtoc_intro"))
    return top


# ---------- notes ----------

def _note_candidates(view: DocView, host: Node, pattern: re.Pattern, min_size: float, colour: str | None,
                     bold_names: list[str]):
    for r in view.regions:
        if not host.start <= r["page_no"] <= host.end or r["layer"] != "body" or not r["text"]:
            continue
        f = r["font"] or {}
        if float(f.get("size") or 0) < min_size or not is_bold(f, bold_names):
            continue
        if colour is not None and f.get("color") in (None, colour):
            continue
        m = pattern.match(join_lines(r["text"]))
        if m:
            yield r, m


def _end_before(nxt_page: int, nxt_y: float, split_y: float, text_before: bool = False) -> int:
    """The previous node ends on the next node's page when running body text comes before the next heading there in
    reading order (e.g. the previous section's last paragraphs, or the other column); a heading set low under only
    pictures, a pull quote or a big figure starts its page, and the previous node ends a page earlier. (`nxt_y` and
    `split_y` are kept for callers; position alone no longer decides.)"""
    return nxt_page if text_before else nxt_page - 1


TEXT_TYPES = ("text", "list", "table", "footnote")


RUNNING_TEXT_MIN_PAGES = 3




def _first_text(view: DocView, lay: Layout) -> dict[int, int]:
    """page -> reading order of the first body text region on it. Text repeated on several pages (a running
    header the layout model left in the body, e.g. "For the financial year ended ...") does not count, nor does
    display text (a pull quote or a big figure, at least `display_text_factor` x the body size), nor a "(continued)"
    header repeating an earlier heading ("38.3 Market Risk (continued)")."""
    body = body_size(view.regions)
    big = (lambda r: body > 0 and float((r["font"] or {}).get("size") or 0) >= lay.display_factor * body)  # noqa: E731
    seen: dict[str, set[int]] = {}
    for r in view.regions:
        if r["layer"] == "body" and r["type"] in TEXT_TYPES and r["text"]:
            seen.setdefault(norm(r["text"]), set()).add(r["page_no"])
    out: dict[int, int] = {}
    for r in view.regions:
        if r["layer"] == "body" and r["type"] in TEXT_TYPES and not big(r) \
                and not lay.continued.search(r["text"] or "") \
                and len(seen.get(norm(r["text"] or ""), ())) < RUNNING_TEXT_MIN_PAGES:
            out[r["page_no"]] = min(out.get(r["page_no"], r["reading_order"]), r["reading_order"])
    return out


def _text_before(first_text: dict[int, int], r: dict) -> bool:
    return first_text.get(r["page_no"], 1 << 30) < r["reading_order"]


def _split_notes(view: DocView, host: Node, rules: dict, colour: str | None, first_text: dict[int, int]) -> None:
    nr, split_y = rules["notes"], rules["headings"]["split_y"]
    continued = re.compile(nr["continued"], re.I)
    heads, last, cont = [], 0, {}
    for r, m in _note_candidates(view, host, re.compile(nr["note"]), nr["note_min_size"], colour,
                                 rules["bold_font_names"]):
        num, title = int(m.group(1)), m.group(2).strip()
        if continued.search(title):
            cont[num] = max(cont.get(num, 0), r["page_no"])   # "(continued)": the note runs at least to this page
        elif num == last + 1:
            heads.append((num, f"{num}. {title}", r))
            last = num
    if len(heads) < nr["min_notes"]:
        return
    kids = []
    for (num, title, r), nxt in zip(heads, heads[1:] + [None]):
        end = host.end if nxt is None else _end_before(nxt[2]["page_no"], nxt[2]["bbox"][1], split_y,
                                                       _text_before(first_text, nxt[2]))
        end = min(host.end, max(end, cont.get(num, 0)))
        kid = Node(title, r["page_no"], max(r["page_no"], end), "note", r["bbox"][1], _size(r, rules["bold_font_names"]),
                   [r["region_id"]], order=r["reading_order"], x=r["bbox"][0])
        _split_subnotes(view, kid, num, rules, colour, first_text)
        kids.append(kid)
    if heads[0][2]["page_no"] > host.start:
        kids.insert(0, Node(host.title + " (intro)", host.start, heads[0][2]["page_no"] - 1, "note_intro"))
    host.nodes = kids


def _split_subnotes(view: DocView, note: Node, num: int, rules: dict, colour: str | None,
                    first_text: dict[int, int]) -> None:
    nr, split_y = rules["notes"], rules["headings"]["split_y"]
    continued, title_start = re.compile(nr["continued"], re.I), re.compile(nr["title_start"])
    subs, last, cont = [], 0, {}
    for r, m in _note_candidates(view, note, re.compile(nr["subnote"]), nr["subnote_min_size"], None,
                                 rules["bold_font_names"]):
        if int(m.group(1)) != num:
            continue
        sub, title = int(m.group(2)), m.group(3).strip()
        if continued.search(title):
            cont[sub] = max(cont.get(sub, 0), r["page_no"])
            continue
        if not title_start.match(title) or sub != last + 1:
            continue
        subs.append((sub, f"{num}.{sub} {title}", r))
        last = sub
    if len(subs) < nr["min_subnotes"]:
        return
    for (sub, title, r), nxt in zip(subs, subs[1:] + [None]):
        end = note.end if nxt is None else _end_before(nxt[2]["page_no"], nxt[2]["bbox"][1], split_y,
                                                       _text_before(first_text, nxt[2]))
        end = min(note.end, max(end, cont.get(sub, 0)))
        note.nodes.append(Node(title, r["page_no"], max(r["page_no"], end), "subnote", r["bbox"][1], _size(r),
                               [r["region_id"]], order=r["reading_order"], x=r["bbox"][0]))


# ---------- section headings ----------

def _junk(title: str, hr: dict) -> bool:
    t = title.strip()
    if re.match(hr["placeholder"], t) or t.endswith("(intro)") or re.match(hr["refer_to"], t, re.I):
        return True
    n = norm(t)
    if n in {g.lower() for g in hr["generic"]}:
        return True
    cjk = len(re.findall(r"[\u4e00-\u9fff]", t))
    # two CJK characters make a word (a country label such as China or Macau); generic words are listed above
    return bool((cjk and cjk < 2 and len(n) < 4) or (not cjk and len(n) < 4))


def _base(title: str, continued: re.Pattern) -> str:
    return norm(continued.sub("", title))


def body_size(regions: list[dict]) -> float:
    """Most common font size of body text regions (0 when unknown)."""
    sizes = Counter(round(float((r["font"] or {}).get("size") or 0), 1) for r in regions
                    if r["type"] == "text" and r["layer"] == "body" and r["font"])
    sizes.pop(0.0, None)
    return sizes.most_common(1)[0][0] if sizes else 0.0


def _figure_dominant(title: str, hr: dict) -> bool:
    """A stat callout such as "33% CAGR" or a figure with a unit: few letters left once numbers, signs and unit
    words are removed."""
    if not hr.get("stat_units"):
        return False
    t = title.lower()
    for u in sorted(hr["stat_units"], key=len, reverse=True):
        u = str(u).lower()
        t = re.sub(r"(?<![a-z])" + re.escape(u) + r"(?![a-z])", " ", t) if u.isascii() else t.replace(u, " ")
    letters = [c for c in t if c.isalpha()]
    return len(letters) < hr.get("min_letters", 2) and bool(re.search(r"\d|%", title))


def _subtitle_line(r: dict, prev: dict | None, nxt: dict | None, gap: float, apart: float) -> bool:
    """A smaller line set directly under the heading just before it, in the same column, and set apart from the text
    that follows: the gap below is at least `apart` times the gap above (a job title under a name). A first subheading
    sits about as close to its own text as to the heading above, or is followed by a table, and stays a heading."""
    if not prev or prev["page_no"] != r["page_no"] or prev["type"] not in ("title", "heading"):
        return False
    if not nxt or nxt["page_no"] != r["page_no"] or nxt["type"] != "text":
        return False
    size = lambda x: float((x["font"] or {}).get("size") or 0)  # noqa: E731
    above = r["bbox"][1] - prev["bbox"][3]
    return (size(prev) - size(r) >= 0.5 and abs(prev["bbox"][0] - r["bbox"][0]) <= 3
            and 0 <= above <= gap and nxt["bbox"][1] - r["bbox"][3] >= apart * max(above, 0.5))


def _inside_table(r: dict, tables: dict[int, list[list[float]]]) -> bool:
    cx, cy = (r["bbox"][0] + r["bbox"][2]) / 2, (r["bbox"][1] + r["bbox"][3]) / 2
    return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in tables.get(r["page_no"], []))


def _not_a_heading(title: str, r: dict, hr: dict, min_size: float, tables: dict) -> bool:
    words = re.findall(r"[A-Za-z]+", title.lower())
    if words and words[-1] in set(hr.get("trailing_words") or ()):
        return True                                               # a fragment such as "More than" (stat callout)
    if hr.get("caption") and re.match(hr["caption"], title):
        return True                                               # "Table 2: ..." caption
    if _inside_table(r, tables):
        return True                                               # a table cell, chart or diagram label
    if _figure_dominant(title, hr):
        return True                                               # "400 wan", "33% CAGR"
    if hr.get("field_line") and re.search(hr["field_line"], title):
        return True                                               # "Dear Fellow Shareholders,", "Appointed: 2017..."
    size = float((r["font"] or {}).get("size") or 0)
    return bool(min_size and size and size < min_size)          # smaller than body text: a label, not a heading




def _card_grid(regions: list[dict], types: list[str], next_of: dict, min_size: float, lay: Layout) -> set[str]:
    """Region ids of same-size headings laid out side by side as cards: a row of `card_row` or more on a page, set
    closer than `card_max_pitch` apart (narrow cards; a three- or four-column page has a wider pitch). A directory
    page, where a heading is followed by entry text smaller than body text (regions, countries), stays."""
    rows: dict[tuple[int, float], list[list[dict]]] = {}
    for r in regions:
        if r["type"] not in types or r["layer"] != "body" or not r["text"]:
            continue
        key = (r["page_no"], round(float((r["font"] or {}).get("size") or 0), 1))
        for row in rows.setdefault(key, []):
            if abs(row[0]["bbox"][1] - r["bbox"][1]) <= lay.row_dy:
                row.append(r)
                break
        else:
            rows[key].append([r])
    size = lambda x: float((x["font"] or {}).get("size") or 0)  # noqa: E731
    out: dict[int, set[str]] = {}
    directory: set[int] = set()
    for (page, _), rs in rows.items():
        for row in rs:
            for r in row:   # a directory page: any heading followed by entry text smaller than body text
                nxt = next_of.get(id(r))
                if nxt is not None and nxt["page_no"] == page and min_size and 0 < size(nxt) < min_size:
                    directory.add(page)
            xs = sorted(r["bbox"][0] for r in row)
            if len(row) >= lay.card_row and max(b - a for a, b in zip(xs, xs[1:])) <= lay.card_max_pitch:
                out.setdefault(page, set()).update(r["region_id"] for r in row)
    return {rid for page, ids in out.items() if page not in directory for rid in ids}


def _callout_or_signature(title: str, r: dict, prev: dict | None, nxt: dict | None, hr: dict) -> bool:
    """A stat-callout label (its own title carries a figure with a unit, or the next region is a figure at least as
    large) or a signatory name (right after a signature image)."""
    if hr.get("figure_unit") and re.search(hr["figure_unit"], title, re.I):
        return True
    if prev is not None and prev["type"] == "signature" and prev["page_no"] == r["page_no"]:
        return True
    if nxt is not None and nxt["page_no"] == r["page_no"] and nxt["text"] and nxt["type"] in ("text", "heading"):
        size = lambda x: float((x["font"] or {}).get("size") or 0)  # noqa: E731
        return size(nxt) >= size(r) and _figure_dominant(join_lines(nxt["text"]), hr)
    return False


def _heading_nodes(view: DocView, rules: dict, skip_pages: set[int]) -> list[tuple[Node, dict]]:
    lay = layout(rules)
    hr = rules["headings"]
    numbered = re.compile(hr["numbered"]) if hr.get("numbered") else None
    min_size = body_size(view.regions) * float(hr.get("min_size_vs_body") or 0)
    tables: dict[int, list[list[float]]] = {}
    for t in view.regions:
        if t["type"] in (hr.get("container_types") or ["table"]):
            tables.setdefault(t["page_no"], []).append(t["bbox"])
    first_text = _first_text(view, lay)
    body = [r for r in view.regions if r["layer"] == "body"]
    prev_of = {id(b): a for a, b in zip([None, *body], body)}
    next_of = {id(a): b for a, b in zip(body, [*body[1:], None])}
    grid = _card_grid(view.regions, hr["types"], next_of, min_size, lay)
    out = []
    for r in view.regions:
        if r["type"] not in hr["types"] or r["layer"] != "body" or not r["text"] or r["page_no"] in skip_pages:
            continue
        title = join_lines(r["text"])
        if _junk(title, hr) or (numbered and numbered.match(title)) \
                or _not_a_heading(title, r, hr, min_size, tables) or r["region_id"] in grid \
                or _callout_or_signature(title, r, prev_of.get(id(r)), next_of.get(id(r)), hr) \
                or _subtitle_line(r, prev_of.get(id(r)), next_of.get(id(r)), float(hr.get("subtitle_gap_pt") or 0),
                                  float(hr.get("subtitle_apart_factor") or 2)):
            continue
        out.append((Node(title, r["page_no"], r["page_no"], "heading", r["bbox"][1],
                         _size(r, rules.get("bold_font_names", [])), [r["region_id"]],
                         text_before=_text_before(first_text, r), order=r["reading_order"], x=r["bbox"][0]), r))
    return out


LEVEL_STEP = 0.005   # below a same-size heading, above any smaller one (sizes differ by >= 0.5 pt; bold adds 0.01)




def same_size_levels(heads: list[Node], bullet: str | None, dy_factor: float = 3.0,
                     lettered: str | None = None, lay: Layout | None = None, in_notes: bool = False) -> None:
    """Give same-size headings a level from layout (sizes are adjusted in place before nesting by size):
    a bullet heading drops one step; a group head (immediately followed in reading order by a same-size heading)
    makes the same-size headings after it, until the next group head or a larger heading, drop one step.
    Dotted numbering drops one step per level below x.y (2.13.6 under a same-size 2.13 heading, 2.13.6.1 under
    2.13.6), and a lettered item ("(c) ...") drops one step below the deepest numbered heading before it."""
    bullet_re = re.compile(bullet) if bullet else None
    letter_re = re.compile(lettered) if lettered else None
    lay = lay or layout({})
    depth, dotted_size = 0, None
    for h in heads:
        m = lay.dotted.match(h.title)
        if m:
            depth, dotted_size = m.group(1).count(".") - 1, h.size
            h.size -= LEVEL_STEP * depth
        elif lay.roman.match(h.title):
            depth, dotted_size = 0, None          # "(II) Other Assets": a group of its own, not under 2.11.4
        elif letter_re and letter_re.match(h.title):
            h.size -= LEVEL_STEP * (depth + 1)
        elif in_notes and dotted_size is not None and h.size <= dotted_size and depth:
            h.size -= LEVEL_STEP * (depth + 1)     # inside notes: an unnumbered sub-heading under the dotted one before it
        elif dotted_size is not None and h.size > dotted_size:
            depth, dotted_size = 0, None
    base = [h.size for h in heads]
    group = None
    for i, h in enumerate(heads):
        nxt = heads[i + 1] if i + 1 < len(heads) else None
        is_head = (nxt is not None and nxt.start == h.start and nxt.order == h.order + 1 and base[i + 1] == base[i]
                   and abs(nxt.x - h.x) <= 3 and 0 < nxt.y - h.y <= dy_factor * base[i])
        if group is not None and (base[i] > group or (base[i] == group and is_head)):
            group = None
        if is_head:
            group = base[i]
        elif group is not None and base[i] == group:
            h.size = base[i] - LEVEL_STEP
        if bullet_re and bullet_re.match(h.title):
            h.size = base[i] - LEVEL_STEP


def _nest(heads: list[Node], parent_end: int, split_y: float, bullet: str | None = None,
          dy_factor: float = 3.0, lettered: str | None = None, lay: Layout | None = None,
          in_notes: bool = False) -> list[Node]:
    """Nest headings by font size (larger = higher; same-size levels from layout), then set each node's end from its
    next sibling."""
    lay = lay or layout({})
    same_size_levels(heads, bullet, dy_factor, lettered, lay, in_notes)
    roots: list[Node] = []
    stack: list[Node] = []
    for h in heads:
        while stack and stack[-1].size <= h.size:
            stack.pop()
        (stack[-1].nodes if stack else roots).append(h)
        stack.append(h)

    def ends(siblings: list[Node], end: int) -> None:
        for a, b in zip(siblings, siblings[1:] + [None]):
            a.end = end if b is None else max(a.start, _end_before(b.start, b.y, split_y, b.text_before))
            a.end = min(a.end, end)
            ends(a.nodes, a.end)

    while _numbering_parents(roots, lay):
        pass
    ends(roots, parent_end)
    return roots


def _numbering_parents(siblings: list[Node], lay: Layout) -> bool:
    """A dotted heading never sits under a dotted heading whose number is not a prefix of its own (2.13.6.5 under
    2.13.6.4): it moves up to follow that heading as a sibling, together with the headings after it in the same list
    (they come later in reading order, so they cannot stay under the old parent). Returns whether anything moved; the
    caller repeats until nothing does, so a heading climbs as many levels as needed."""
    moved_any = False
    i = 0
    while i < len(siblings):
        parent = siblings[i]
        pm = lay.dotted.match(parent.title)
        if pm:
            for j, k in enumerate(parent.nodes):
                km = lay.dotted.match(k.title)
                if km and not km.group(1).startswith(pm.group(1) + "."):
                    siblings[i + 1:i + 1] = parent.nodes[j:]
                    parent.nodes = parent.nodes[:j]
                    moved_any = True
                    break
        moved_any |= _numbering_parents(parent.nodes, lay)
        i += 1
    return moved_any


def _dedupe(nodes: list[Node], continued: re.Pattern) -> list[Node]:
    out: list[Node] = []
    for n in sorted(nodes, key=lambda x: (x.start, x.y)):
        if out and _base(out[-1].title, continued) == _base(n.title, continued) and n.start <= out[-1].end + 1:
            out[-1].end = max(out[-1].end, n.end)
            out[-1].nodes += n.nodes
            out[-1].region_ids += n.region_ids
        else:
            out.append(n)
    for n in out:
        n.title = continued.sub("", n.title).strip()
        n.nodes = _dedupe(n.nodes, continued)
    return out


def _host(containers: list[Node], node: Node) -> Node | None:
    """The container a heading belongs to: among those covering its page, the one starting last before it in reading
    order (a note's subnote over the note, a later section over an earlier one ending on the same page). Reading
    order, not height: on a two-column page a later heading can sit higher in the other column."""
    here = [c for c in containers if c.start <= node.start <= c.end and (c.start, c.order) <= (node.start, node.order)]
    return max(here, key=lambda c: (c.start, c.order)) if here else None


def _attach(containers: list[Node], heads: list[tuple[Node, dict]], rules: dict, taken_titles: set[str]) -> None:
    hr = rules["headings"]
    lay = layout(rules)
    continued = re.compile(rules["notes"]["continued"], re.I)
    by_host: dict[int, list[Node]] = {}
    hosts = {id(c): c for c in containers}
    # a note's subnotes by number ("2.11" -> node), per note, so two note sets reusing numbers stay apart
    note_of: dict[int, Node] = {}
    subnotes: dict[tuple[int, str], Node] = {}
    for c in containers:
        if c.origin == "note":
            for k in c.nodes:
                if k.origin == "subnote":
                    note_of[id(k)] = c
                    subnotes[(id(c), k.title.split(" ", 1)[0])] = k
    for node, _ in heads:
        host = _host(containers, node)
        if host is None:
            continue
        m = lay.dotted.match(node.title)
        note = host if host.origin == "note" else note_of.get(id(host))
        if m and note is not None:
            # inside a note, a dotted number names its subnote ("2.11.5" -> "2.11"), whatever position suggests
            host = subnotes.get((id(note), ".".join(m.group(1).split(".")[:2]))) or host
        t = _base(node.title, continued)      # "Overview (continued)" is the existing "Overview", not a new node
        if t in taken_titles or t == _base(host.title, continued) or norm(host.title).startswith(t):
            continue
        by_host.setdefault(id(host), []).append(node)
    for hid, nodes in by_host.items():
        host = hosts[hid]
        # a title repeated within one section without a "(continued)" mark is a field label, not a heading -- except
        # a numbered title ("2.13.6 Measurement"), which is the heading reprinted on a later page: keep its first copy
        plain = Counter(_base(n.title, continued) for n in nodes if not continued.search(n.title))
        first_numbered: set[str] = set()
        kept_nodes = []
        for n in nodes:
            base = _base(n.title, continued)
            if plain[base] >= 2:
                if not lay.dotted.match(n.title) or base in first_numbered:
                    continue
                first_numbered.add(base)
            kept_nodes.append(n)
        nodes = kept_nodes
        # a "(continued)" repeat of a heading seen earlier in this section is not a node of its own, whatever its
        # weight (a light repeat of a bold heading would otherwise nest under it)
        seen: set[str] = set()
        kept_heads = []
        for n in nodes:                         # reading order (columns), not page position
            base = _base(n.title, continued)
            if continued.search(n.title) and base in seen:
                continue
            seen.add(base)
            kept_heads.append(n)
        nodes = kept_heads
        kept = host.nodes                       # a note's subnotes: new headings come before the first of them
        end = host.end if not kept else max(host.start, _end_before(kept[0].start, kept[0].y, hr["split_y"],
                                                                     kept[0].text_before))
        new = _dedupe(_nest(nodes, end, hr["split_y"], hr.get("bullet"), hr.get("group_dy_factor", 3),
                            hr.get("lettered"), lay, host.origin in ("note", "subnote")), continued)
        host.nodes = new + kept
        if not kept and host.origin not in ("note", "subnote") and len(host.nodes) == 1 and host.nodes[0].start == host.start and host.nodes[0].end == host.end \
                and not host.nodes[0].nodes:
            host.nodes = []


def _leaves(nodes: list[Node]):
    for n in nodes:
        if n.nodes:
            yield from _leaves(n.nodes)
        else:
            yield n


def _all(nodes: list[Node]):
    for n in nodes:
        yield n
        yield from _all(n.nodes)


def _merge_wrapped(view: DocView, rules: dict) -> DocView:
    """Join a title wrapped over two heading regions ("2. Material Accounting" / "Policy Information (continued)",
    "Pursuing Sustainable" / "Growth"): the next region in reading order on the same page, a heading of the same size
    and weight, starting directly below (within `wrap_gap` x the size) and not left of the first line, that does not
    start a number or a bullet. The joined region keeps the first region's id and box top."""
    types = rules["headings"]["types"]
    lay = layout(rules)
    bullet = re.compile(rules["headings"].get("bullet") or r"^$")
    numbered = re.compile(r"^\(?\d|^\([a-zA-Z]{1,4}\)\s")
    out: list[dict] = []
    for r in view.regions:
        prev = out[-1] if out else None
        if prev is not None and r["type"] in types and prev["type"] in types and r["layer"] == prev["layer"] == "body" \
                and r["page_no"] == prev["page_no"] and r["text"] and prev["text"]:
            f, g = prev["font"] or {}, r["font"] or {}
            size = float(f.get("size") or 0)
            gap = r["bbox"][1] - prev["bbox"][3]
            if size and abs(size - float(g.get("size") or 0)) < 0.1 and bool(f.get("bold")) == bool(g.get("bold")) \
                    and f.get("name") == g.get("name") and -1 <= gap <= lay.wrap_gap * size \
                    and prev["bbox"][0] - 2 <= r["bbox"][0] <= (prev["bbox"][0] + prev["bbox"][2]) / 2 \
                    and not numbered.match(join_lines(r["text"])) and not bullet.match(join_lines(r["text"])) \
                    and not lay.continued.search(prev["text"]):   # "... (continued)" is a complete title
                out[-1] = {**prev, "text": join_lines(prev["text"]) + " " + join_lines(r["text"]),
                           "bbox": [min(prev["bbox"][0], r["bbox"][0]), prev["bbox"][1],
                                    max(prev["bbox"][2], r["bbox"][2]), r["bbox"][3]]}
                continue
        out.append(r)
    return replace(view, regions=out)


def build_annual_report_tree(view: DocView, rules: dict, notes: list | None = None) -> list[Node]:
    """Annual-report tree; `notes` collects build gaps (page labels, fallback, font colour)."""
    notes = notes if notes is not None else []
    view = _merge_wrapped(view, rules)
    colour = body_colour(view.regions)
    if colour is None:
        notes.append({"code": "font_colour_unavailable",
                      "detail": "font colour not in package; note headings use numbering, size and weight only"})
    toc_page = _find_toc_page(view, rules["toc"])
    if toc_page is None:
        notes.append({"code": "tree_fallback_generic", "detail": "no contents page found; the tree is built from "
                      "headings only"})
        return build_generic_tree(view, rules)
    nav = nav_pages(view, rules["nav_page_max_chars"]) | {toc_page} | set(_sub_toc_pages(view, toc_page, rules["toc"]))
    top = _skeleton(view, rules, toc_page, nav, notes)
    if top is None:
        return build_generic_tree(view, rules)
    section = re.compile(rules["notes"]["section"])
    first_text = _first_text(view, layout(rules))
    for leaf in list(_leaves(top)):
        if section.search(leaf.title):
            _split_notes(view, leaf, rules, colour, first_text)
    taken = {norm(n.title) for n in _all(top)}
    containers = [c for c in _all(top) if not c.nodes or c.origin == "note"]
    _attach(containers, _heading_nodes(view, rules, nav), rules, taken)
    return top


def build_generic_tree(view: DocView, rules: dict, notes: list | None = None) -> list[Node]:
    view = _merge_wrapped(view, rules)
    hr = rules["headings"]
    nav = nav_pages(view, rules.get("nav_page_max_chars", 30))
    continued = re.compile(rules["notes"]["continued"], re.I)
    heads = [n for n, _ in _heading_nodes(view, rules, nav)]
    return _dedupe(_nest(heads, view.page_count, hr["split_y"], hr.get("bullet"), hr.get("group_dy_factor", 3),
                         hr.get("lettered"), layout(rules)),
                   continued)


def flatten(nodes: list[Node], doc_id: str, tree_source: str = "regions") -> list[TreeNode]:
    out: list[TreeNode] = []

    def walk(ns: list[Node], parent: str | None, depth: int) -> None:
        for n in ns:
            node_id = f"{doc_id}:{tree_source}:{len(out):04d}"
            out.append(TreeNode(node_id, parent, depth, len(out), n.title, n.start, n.end, n.origin,
                                list(n.region_ids), section_type=n.section_type, section_rule=n.section_rule))
            walk(n.nodes, node_id, depth + 1)

    walk(nodes, None, 1)
    return out
