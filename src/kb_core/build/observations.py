"""Observation extraction for annual reports (port of kb profiles/annual_report/observations.py; design §3.2).

Target tables: those whose cells contain the profile's target title (five-year summary, MD&A overview). Years: the
header columns, else the last run of years before the target title in the page text, mapped in order to the first
value columns. Units: a section row (no values) sets the unit for the rows below; a unit in the row label wins for
that row. Row label -> concept: exact match after normalisation, core metrics (facts.yaml) only. Values are plain
numbers as kb parsed them (a parenthesised number is negative).
"""

import re
from decimal import Decimal
from functools import cache

import yaml

from kb_core.build.cells import Units, unit_of
from kb_core.build.concepts import _squash, clean_label, norm
from kb_core.domains import domain_dir
from kb_core.paths import data_dir

PLAIN = re.compile(r"\(?-?[\d,]+(?:\.\d+)?\)?")


@cache
def observation_rules(doc_type: str) -> dict:
    path = data_dir("profiles") / doc_type / "observations.yaml"
    if not path.exists():
        return {}
    r = yaml.safe_load(path.read_text())
    return {**r, "_target": re.compile(r["target"]), "_year": re.compile(r["year"]),
            "_restated": re.compile(r["restated"], re.I), "_footnoted": re.compile(r["footnoted_year"])}


@cache
def fact_concepts(domain: str = "banking") -> tuple[str, ...]:
    return tuple(yaml.safe_load((domain_dir(domain) / "facts.yaml").read_text())["concepts"])


def _table_text(it) -> str:
    return " ".join([*it.columns, *(r.label for r in it.rows)])


def header_years(it, page_text: str, report_year: int, rules: dict) -> list[int]:
    years = [int(m.group(1)) for col in it.columns[1:] for m in [rules["_year"].search(col)] if m]
    if len(years) < 2:
        flat = re.sub(r"\s+", " ", page_text or "")
        m = rules["_target"].search(flat)
        before = flat[:m.start()] if m else flat[:300]
        found = [int(y) for y in rules["_year"].findall(before[-200:])]
        run: list[int] = []
        for y in reversed(found):
            if run and abs(run[0] - y) != 1:
                break
            run.insert(0, y)
        years = run
    years = [y for y in years if report_year - rules["year_window"] <= y <= report_year]
    return years if len(years) >= 2 and len(set(years)) == len(years) else []


def footnoted_years(it, page_text: str, rules: dict) -> set[int]:
    flat = re.sub(r"\s+", " ", page_text or "")
    if not rules["_restated"].search(flat):
        return set()
    m = rules["_target"].search(flat)
    window = " ".join(it.columns) + " " + (flat[:m.start()][-200:] if m else flat[:300])
    return {int(y) for y in rules["_footnoted"].findall(window)}


def _value(raw: str) -> Decimal | None:
    raw = re.sub(r"\s+", " ", re.sub(r"\*\*|<br>", " ", raw or "")).strip()
    if not PLAIN.fullmatch(raw):
        return None
    v = Decimal(raw.strip("()").replace(",", ""))
    return -v if raw.startswith("(") and raw.endswith(")") else v


def _concept_index(spec: dict, domain: str) -> dict[str, dict]:
    core = set(fact_concepts(domain))
    out: dict[str, dict] = {}
    for c in spec["concepts"]:
        if c["id"] in core:
            for s in [*(c.get("variants") or ()), *(c.get("row_labels") or ())]:
                out.setdefault(norm(s), c)
    return out


def _period(c: dict, fy: int) -> str:
    return f"I:{fy}-12-31" if c["period_kind"] == "instant" else f"D:{fy}-01-01:{fy}-12-31"


def _snippet(page_text: str, label: str) -> str:
    flat = re.sub(r"\s+", " ", page_text or "")
    squashed, pos = _squash(flat)
    key, _ = _squash(label[:30])
    i = squashed.find(key) if key else -1
    return flat[pos[i]:pos[i] + 160] if i >= 0 else ""


def extract(doc: dict, tables: list[dict], spec: dict, units: Units, rules: dict, domain: str = "banking") -> list[dict]:
    """tables: [{table, interpreted, page_text, page_label}] of one document -> observation rows."""
    if not rules:
        return []
    index = _concept_index(spec, domain)
    report_year, entity = int(doc["fiscal_year"]), doc["issuer_id"]
    out = []
    for t in tables:
        it, table, page_text = t["interpreted"], t["table"], t["page_text"] or ""
        if not rules["_target"].search(_table_text(it)):
            continue
        years = header_years(it, page_text, report_year, rules)
        if not years:
            continue
        restated = footnoted_years(it, page_text, rules)
        unit = (unit_of(" ".join(it.columns), units) or unit_of(re.sub(r"\s+", " ", page_text)[:300], units)
                or (units.amount_unit, rules["default_scale"]))
        r = -1
        for row in it.rows:
            label = clean_label(row.label)
            if not label:
                continue
            r += 1
            raws = [v.raw for v in row.values[:len(years)]]
            values = [_value(x) for x in raws]
            if all(v is None for v in values):
                unit = unit_of(label, units) or unit
                continue
            row_unit = unit_of(label, units) if units.row_unit.search(label) else None
            u, scale = row_unit or unit
            c = index.get(norm(units.row_unit_strip.sub("", label))) or index.get(norm(label))
            if c is None or u in units.skip_units:
                continue
            for col, (fy, v, raw) in enumerate(zip(years, values, raws)):
                if v is None:
                    continue
                out.append({"obs_id": f"{table['table_id']}:r{r:02d}:c{col}", "doc_id": doc["doc_id"],
                            "report_year": report_year, "table_id": table["table_id"], "page_no": table["page_no"],
                            "page_label": t.get("page_label"), "row_label": label, "concept_id": c["id"],
                            "entity_id": entity, "fiscal_year": fy, "period_id": _period(c, fy),
                            "value": v * (Decimal(10) ** scale), "unit": u, "raw_value": raw,
                            "raw_scale": str(Decimal(10) ** scale), "snippet": _snippet(page_text, label),
                            "restated_note": fy in restated})
    return out
