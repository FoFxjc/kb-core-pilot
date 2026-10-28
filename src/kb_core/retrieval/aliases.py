"""Query-side concept recognition and alias expansion (port of kb service/aliases.py; domain pack concepts.yaml).

When a wording of a metric (variants or query_only) appears in the query, the tokens of its expandable report
wordings are added to the search terms and marked in scope.query_term_sources. query_only and row_labels only
recognise a metric; wordings containing another wording of the same metric are not expanded. A matched metric is one
coverage unit. KB_CORE_ALIASES=off disables expansion (eval comparisons only).
"""

import re
from functools import cache

import yaml

from kb_core.build.tokenize import tokens
from kb_core.domains import domain_dir

CJK = re.compile(r"[\u4e00-\u9fff]")


@cache
def _spec(domain: str) -> dict:
    path = domain_dir(domain) / "concepts.yaml"
    if not path.exists():
        return {"version": None, "concepts": [], "edges": []}
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader)


@cache
def table(domain: str) -> tuple[int | None, tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]]:
    spec = _spec(domain)
    concepts = []
    for c in spec["concepts"]:
        reported = tuple(c.get("variants") or ())
        recognise = tuple(dict.fromkeys(x for x in (*(c.get("query_only") or ()), *(c.get("row_labels") or ()))
                                        if x not in reported))
        concepts.append((c["id"], reported, recognise))
    return (int(spec["version"]) if spec["version"] is not None else None), tuple(concepts)


def concept_spec(domain: str) -> dict[str, dict]:
    return {c["id"]: c for c in _spec(domain)["concepts"]}


@cache
def _narrower(domain: str) -> dict[str, tuple[str, ...]]:
    down: dict[str, list[str]] = {}
    for e in _spec(domain).get("edges") or ():
        if e["relation"] == "broader":
            down.setdefault(e["dst"], []).append(e["src"])
    out = {}
    for top in down:
        seen, stack = [], list(down[top])
        while stack:
            c = stack.pop(0)
            if c not in seen:
                seen.append(c)
                stack += down.get(c, [])
        out[top] = tuple(sorted(seen))
    return out


def narrower(concept_id: str, domain: str) -> list[str]:
    return list(_narrower(domain).get(concept_id, ()))


def _pattern(variant: str) -> re.Pattern:
    v = variant.lower()
    if CJK.search(v):  # Chinese wording: whitespace does not matter
        return re.compile(r"\s*".join(map(re.escape, v.replace(" ", ""))))
    parts = [re.escape(p) for p in re.split(r"[\s\-]+", v) if p]
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-]+".join(parts) + r"(?![a-z0-9])")


@cache
def _excludes(domain: str) -> dict[str, tuple[re.Pattern, ...]]:
    return {c["id"]: tuple(_pattern(x) for x in c.get("exclude") or ()) for c in _spec(domain)["concepts"]}


@cache
def _patterns(domain: str) -> tuple[tuple[str, str, re.Pattern], ...]:
    return tuple((cid, v, _pattern(v)) for cid, variants, query_only in table(domain)[1] for v in variants + query_only)


def expandable(variants: tuple[str, ...]) -> list[str]:
    low = [v.lower() for v in variants]
    return [v for v, lv in zip(variants, low) if not any(o != lv and o in lv for o in low)]


def enabled() -> bool:
    """KB_CORE_ALIASES (evaluation switch; on unless the running settings turn it off)."""
    from kb_core.config import current

    s = current()
    return s.aliases if s is not None else True


def matches(query: str, domain: str) -> list[dict]:
    """Metrics named in the query: [{id, variant, span}]; overlapping spans of different metrics keep the longer."""
    q = query.lower()
    excluded = {cid: [m.span() for p in pats for m in p.finditer(q)] for cid, pats in _excludes(domain).items()}
    hits = []
    for cid, v, pat in _patterns(domain):
        for m in pat.finditer(q):
            s, e = m.span()
            if any(xs <= s and e <= xe for xs, xe in excluded.get(cid, ())):
                continue
            hits.append({"id": cid, "variant": v, "span": (s, e)})
    hits.sort(key=lambda h: (-(h["span"][1] - h["span"][0]), h["span"][0], h["id"], h["variant"]))
    kept, taken = [], []
    for h in hits:
        s, e = h["span"]
        same = [k for k in kept if k["id"] == h["id"]]
        if any(s < te and ts < e for ts, te, tid in taken if tid != h["id"]):
            continue
        if same and any(k["variant"] == h["variant"] for k in same):
            continue
        kept.append(h)
        taken.append((s, e, h["id"]))
    return kept


def expand(query: str, domain: str) -> tuple[list[str], list[dict], list[dict]]:
    """(search terms, term sources, alias units) — see kb service/aliases.py expand()."""
    terms = list(dict.fromkeys(tokens(query, domain)))
    sources = [{"term": t, "source": "query", "alias_id": None, "variant": None} for t in terms]
    units: list[dict] = []
    if not enabled():
        return terms, sources, units
    spec = {cid: (vs, qo) for cid, vs, qo in table(domain)[1]}
    by_id: dict[str, list[dict]] = {}
    for h in matches(query, domain):
        by_id.setdefault(h["id"], []).append(h)
    for cid in sorted(by_id):
        typed = [list(dict.fromkeys(tokens(h["variant"], domain))) for h in by_id[cid]]
        reported, query_only = spec[cid]
        units.append({"id": cid, "typed": typed,
                      "variants": [list(dict.fromkeys(tokens(v, domain))) for v in reported + query_only],
                      "concepts": [cid] + narrower(cid, domain)})
        for v in expandable(reported):
            for t in dict.fromkeys(tokens(v, domain)):
                if t not in terms:
                    terms.append(t)
                    sources.append({"term": t, "source": "alias", "alias_id": cid, "variant": v})
    return terms, sources, units


def synonym_units(query_terms: list[str], synonyms: dict, absorbed: set[str] | None = None) -> tuple[list[str], list[dict]]:
    """Word-level synonyms (round 2 W2, class F1): (extra search terms, coverage units). A query word with synonyms
    becomes one coverage unit hit by the word or any synonym, so a synonym never counts twice. A word already inside a
    matched metric's wording (`absorbed`, e.g. "earnings" in "earnings per share") belongs to that metric's unit and
    gets no synonym unit."""
    extra: list[str] = []
    units: list[dict] = []
    for t in query_terms:
        if absorbed and t in absorbed:
            continue
        subs = [s for s in synonyms.get(t, ()) if s != t]
        if not subs:
            continue
        units.append({"kind": "synonym", "id": t, "typed": [[t]], "variants": [[t]] + [[s] for s in subs]})
        extra += [s for s in subs if s not in query_terms and s not in extra]
    return extra, units


def clear_caches() -> None:
    for fn in (_spec, table, _narrower, _excludes, _patterns):
        fn.cache_clear()
