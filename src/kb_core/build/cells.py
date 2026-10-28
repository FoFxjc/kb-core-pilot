"""Cell values (design §3.2): numbers, parenthesised negatives, percent signs, magnitude suffixes, currency signs and
no-value symbols. The rules come from the domain pack's units.yaml (kb's unit patterns plus the `cells` block)."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import cache

import yaml

from kb_core.domains import domain_dir

NUMBER = re.compile(r"^\(?-?\d[\d,]*(?:\.\d+)?\)?$")
FOOTNOTE = re.compile(r"\s*\(\d\)$|\s*\*+$")


@dataclass(frozen=True)
class Units:
    amount_unit: str
    patterns: tuple            # ((regex, unit, scale exponent), ...)
    row_unit: re.Pattern
    row_unit_strip: re.Pattern
    skip_units: frozenset
    table_unit_hint: re.Pattern
    nil: frozenset
    currency: re.Pattern
    suffix: dict
    indent_step_pt: float


@dataclass(frozen=True)
class Value:
    raw: str
    num: Decimal | None
    nil: bool = False
    negative: bool = False
    percent: bool = False
    unit: str | None = None
    scale: int = 0             # power of ten written in the cell itself (S$1,443m -> 6)


def _exp(scale: str) -> int:
    d = Decimal(scale)
    return d.adjusted() if d != 0 else 0


@cache
def load_units(domain: str) -> Units:
    spec = yaml.safe_load((domain_dir(domain) / "units.yaml").read_text())
    cells = spec.get("cells") or {}
    return Units(
        amount_unit=spec["amount_unit"],
        patterns=tuple((re.compile(p["pattern"], re.I if p.get("ignore_case") else 0), p["unit"], _exp(p["scale"]))
                       for p in spec["patterns"]),
        row_unit=re.compile(spec["row_unit"], re.I), row_unit_strip=re.compile(spec["row_unit_strip"], re.I),
        skip_units=frozenset(spec.get("skip_units") or ()), table_unit_hint=re.compile(spec["table_unit_hint"], re.I),
        nil=frozenset(str(x).lower() for x in cells.get("nil", ())),
        currency=re.compile(r"^(?:" + cells.get("currency", r"\$") + r")\s*"),
        suffix={str(k).lower(): int(v) for k, v in (cells.get("suffix") or {}).items()},
        indent_step_pt=float(cells.get("indent_step_pt", 4)))


def unit_of(text: str, units: Units) -> tuple[str, int] | None:
    """(unit, scale exponent) from a unit wording (section row, header, row label); first pattern wins."""
    for pat, unit, scale in units.patterns:
        if pat.search(text or ""):
            return unit, scale
    return None


def parse_cell(text: str | None, units: Units) -> Value:
    raw = re.sub(r"\*\*|<br>", " ", text or "")
    raw = re.sub(r"\s+", " ", raw).strip()
    if raw.lower() in units.nil or raw == "":
        return Value(raw, None, nil=True)
    s = FOOTNOTE.sub("", raw)
    unit, scale, percent = None, 0, False
    m = units.currency.match(s)
    if m:
        unit, s = units.amount_unit, s[m.end():]
    if s.endswith("%"):
        percent, unit, s = True, "pct", s[:-1].strip()
    low = s.lower()
    for suf in sorted(units.suffix, key=len, reverse=True):
        if low.endswith(suf) and NUMBER.match(s[:-len(suf)].strip() or "x"):
            scale, s = units.suffix[suf], s[:-len(suf)].strip()
            unit = unit or units.amount_unit
            break
    if not NUMBER.match(s):
        return Value(raw, None)
    neg = s.startswith("(") and s.endswith(")")
    try:
        num = Decimal(s.strip("()").replace(",", ""))
    except InvalidOperation:
        return Value(raw, None)
    return Value(raw, -num if neg else num, negative=neg or num < 0, percent=percent, unit=unit, scale=scale)
