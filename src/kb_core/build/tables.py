"""Table interpretation (design §3.2): intake cells (original text) -> header columns, labelled rows with parsed values,
row paths from label indentation, a unit hint, and continued-table merges.

Row paths: in the label column, a cell's indent is its bbox x0 minus the smallest x0 of that column's label cells;
indents closer than `indent_step_pt` (units.yaml) are one level; a row's path is the labels of the nearest preceding
rows at each shallower level (kb pipeline/tables.py behaviour). Cells without a bbox give a flat path.
Continued tables follow intake's `continued_hint`: continued_heading -> merged, same_first_row -> hint only.
"""

from dataclasses import dataclass, field

from kb_core.build.cells import Units, Value, parse_cell, unit_of


@dataclass
class Row:
    r: int
    label: str
    path: list[str]
    values: list[Value]


@dataclass
class InterpretedTable:
    table_id: str
    header_rows: list[list[str]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    unit_hint: str | None = None
    is_artifact: bool = False
    indent_unavailable: bool = False

    def to_json(self) -> dict:
        return {"header_rows": self.header_rows, "columns": self.columns, "unit_hint": self.unit_hint,
                "is_artifact": self.is_artifact, "indent_unavailable": self.indent_unavailable,
                "rows": [{"r": r.r, "label": r.label, "path": r.path,
                          "values": [{"raw": v.raw, "num": str(v.num) if v.num is not None else None, "nil": v.nil,
                                      "percent": v.percent, "unit": v.unit, "scale": v.scale} for v in r.values]}
                         for r in self.rows]}


@dataclass
class Merge:
    part_table_ids: list[str]
    reason: str
    decision: str            # merged | hint
    header_from: str | None = None


def _grid(table: dict) -> list[list[dict | None]]:
    grid: list[list[dict | None]] = [[None] * table["n_cols"] for _ in range(table["n_rows"])]
    for c in table["cells"]:
        for r in range(c["r"], min(c["r"] + c.get("rs", 1), table["n_rows"])):
            for k in range(c["c"], min(c["c"] + c.get("cs", 1), table["n_cols"])):
                grid[r][k] = c
    return grid


def _text(c: dict | None) -> str:
    return " ".join((c or {}).get("text", "").split()) if c and c.get("text") else ""


def interpret(table: dict, context_text: str, units: Units) -> InterpretedTable:
    out = InterpretedTable(table["table_id"])
    grid = _grid(table)
    header_n = 0
    for row in grid:                       # leading rows whose cells are all header cells (or empty)
        cells = [c for c in row if c]
        if cells and all(c["is_header"] for c in cells):
            header_n += 1
        else:
            break
    out.header_rows = [[_text(c) for c in row] for row in grid[:header_n]]
    out.columns = []
    for k in range(table["n_cols"]):
        parts = []
        for row in grid[:header_n]:
            t = _text(row[k])
            if t and (not parts or parts[-1] != t):
                parts.append(t)
        out.columns.append(" ".join(parts))
    body = grid[header_n:]
    labels = [row[0] if row else None for row in body]
    xs = [c["bbox"][0] for c in labels if c and c.get("bbox") and _text(c)]
    out.indent_unavailable = any(c and _text(c) and not c.get("bbox") for c in labels)
    x_min = min(xs) if xs else 0.0
    step = units.indent_step_pt
    stack: list[tuple[int, str]] = []
    numeric = 0
    for i, row in enumerate(body):
        label_cell = row[0] if row else None
        label = _text(label_cell)
        values = [parse_cell(_text(c), units) for c in row[1:]]
        numeric += sum(1 for v in values if v.num is not None)
        if not label and all(v.nil for v in values):
            continue
        if out.indent_unavailable or not label_cell or not label_cell.get("bbox"):
            level = 0
        else:
            level = int(round((label_cell["bbox"][0] - x_min) / step)) if step else 0
        while stack and stack[-1][0] >= level:
            stack.pop()
        path = [t for _, t in stack] + [label]
        if label:
            stack.append((level, label))
        out.rows.append(Row(header_n + i, label, path if not out.indent_unavailable else [label], values))
    head_text = " ".join(out.columns) + " " + " ".join(r.label for r in out.rows[:3])
    for text in (head_text, context_text or ""):
        m = units.table_unit_hint.search(text)
        if m:
            out.unit_hint = m.group(1)
            break
    out.is_artifact = numeric == 0
    return out


def row_unit(label: str, units: Units) -> tuple[str, int] | None:
    return unit_of(label, units) if units.row_unit.search(label or "") else None


def merge_continued(tables: list[dict]) -> list[Merge]:
    """Chains of intake continued_hint links. continued_heading links form one merged table (all parts, first part's
    header when later parts lack one); a same_first_row link is recorded as a hint only."""
    by_id = {t["table_id"]: t for t in tables}
    nxt: dict[str, str] = {}
    out: list[Merge] = []
    for t in tables:
        h = t.get("continued_hint")
        if not h or h["table_id"] not in by_id:
            continue
        if h["reason"] == "continued_heading":
            nxt[h["table_id"]] = t["table_id"]
        else:
            out.append(Merge([h["table_id"], t["table_id"]], h["reason"], "hint"))
    heads = [tid for tid in nxt if tid not in nxt.values()]
    for head in heads:
        parts = [head]
        while parts[-1] in nxt:
            parts.append(nxt[parts[-1]])
        out.append(Merge(parts, "continued_heading", "merged", header_from=head))
    return sorted(out, key=lambda m: m.part_table_ids)
