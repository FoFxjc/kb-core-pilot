"""Number check for live chat answers (round 2, W4): every number in the answer must be found in the evidence the
agent read in this session (the tool results), allowing for thousands separators, rounding, sign and the usual
unit scales (thousand / million / billion, percent, the Chinese yi, 100 million).

The check is deterministic and only marks numbers; it never rewrites the answer. What it does not prove: that a
found number belongs to the metric and year the sentence claims, or that a computed number (a difference, a ratio)
is right. Years, page numbers, single digits and numbers inside identifiers (doc_ids, FY2025) are not checked.

Evidence is the content of tool results (text, tables, snippets, values), not their bookkeeping (pages, ranks,
scores, timings, ids): a made-up number must not pass because it matches a page number or a score. A scaled match
(million to billion, ratio to percent) needs at least two significant digits in the answer; an explicit minus sign
must match a negative value.
"""

import json

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# A number not glued to an identifier on the left (doc ids such as ocbc-group_ar_2025_en, FY2025) and not
# continuing into one on the right. Units written right after it (7.6bn, 15m, 2.05%) are allowed.
_NUM = re.compile(r"(?<![A-Za-z0-9_.])([-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?![\d_]|\.\d|,\d{3})")
_PAGE_BEFORE = re.compile(r"(?:\bpages?|\bpp?\.|\bp|\u7b2c|\u9875\u7801)\s*[-–\d, ]*$", re.IGNORECASE)
_PAGE_AFTER = re.compile(r"^\s*(?:[-–]\s*\d+\s*)?\u9875")
_SCALES = (Decimal(1), Decimal("0.001"), Decimal("0.000001"), Decimal(1000), Decimal(1000000), Decimal("0.01"),
           Decimal(100))


def _value(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", "").replace("−", "-").lstrip("+"))
    except InvalidOperation:
        return None


def _decimals(text: str) -> int:
    return len(text.split(".", 1)[1]) if "." in text else 0


# result keys that carry bookkeeping, not content
_META = {"page_no", "page_range", "page_label_range", "page_label", "start_page", "end_page", "score", "rank", "ms",
         "trace_id", "node_id", "doc_id", "parent_id", "table_id", "region_id", "concept_id", "depth", "chars", "n",
         "bbox", "width", "height", "reading_order", "n_sources", "fiscal_year", "fiscal_years", "page_count",
         "confidence", "coverage", "image", "section_type", "tier", "status", "lang", "basis"}


def evidence_numbers(texts: list[str]) -> set[Decimal]:
    """Signed numbers written in free text."""
    out: set[Decimal] = set()
    for t in texts:
        for m in _NUM.finditer(t):
            v = _value(m.group(1))
            if v is not None:
                out.add(v)
    return out


def _walk(node, out: list, key: str | None = None) -> None:
    if key in _META:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            _walk(v, out, k)
    elif isinstance(node, list):
        for v in node:
            _walk(v, out, key)
    elif isinstance(node, str):
        out.append(node)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        out.append(repr(node))


def evidence_from_tool_results(contents: list[str]) -> set[Decimal]:
    """Numbers in the content of tool results as the agent received them (a JSON body, maybe followed by text).
    Only the `results` of a body count, minus bookkeeping keys; text that is not JSON counts as it is."""
    strings: list[str] = []
    for c in contents:
        try:
            body, _end = json.JSONDecoder().raw_decode(c)
        except ValueError:
            strings.append(c)
            continue
        if isinstance(body, dict):
            _walk(body.get("results") or [], strings)
    return evidence_numbers(strings)


def _skip_reason(answer: str, m: re.Match, value: Decimal) -> str | None:
    raw = m.group(1)
    after = answer[m.end():m.end() + 3]
    is_percent = after.lstrip().startswith("%")
    if "." not in raw and "," not in raw and not is_percent:
        if 1900 <= value <= 2100:
            return "year"
        if abs(value) < 10:
            return "small integer"
    if _PAGE_BEFORE.search(answer[max(0, m.start() - 24):m.start()]) or _PAGE_AFTER.match(answer[m.end():]):
        return "page"
    return None


def _significant(raw: str) -> int:
    return len(raw.replace(",", "").lstrip("+-\u2212").replace(".", "").lstrip("0"))


def _found(raw: str, value: Decimal, evidence: set[Decimal]) -> bool:
    signed = raw.lstrip()[:1] in ("-", "\u2212")           # "-0.9%": only a negative value matches
    target = value if signed else abs(value)
    quantum = Decimal(1).scaleb(-_decimals(raw))
    scaled_ok = _significant(raw) >= 2
    for e in evidence:
        e = e if signed else abs(e)
        for scale in _SCALES:
            if scale != 1 and not scaled_ok:
                continue
            if (e * scale).quantize(quantum, rounding=ROUND_HALF_UP) == target:
                return True
    return False


def check_numbers(answer: str, evidence: set[Decimal]) -> dict:
    """{checked, verified, unverified, skipped}: each number with its text and the sentence fragment around it."""
    verified, unverified, skipped = [], [], 0
    for m in _NUM.finditer(answer):
        raw = m.group(1)
        value = _value(raw)
        if value is None or _skip_reason(answer, m, value):
            skipped += 1
            continue
        item = {"text": raw, "context": answer[max(0, m.start() - 40):m.end() + 20].replace("\n", " ").strip()}
        (verified if _found(raw, value, evidence) else unverified).append(item)
    return {"checked": len(verified) + len(unverified), "verified": verified, "unverified": unverified,
            "skipped": skipped, "evidence_numbers": len(evidence)}
