"""resolve_concept: resolve a term (port of kb service/concepts.py; api-contract §5.4). Deterministic: exact match on
concept_id or normalised alias, then prefix match; no fuzzy matching. Unknown terms get similar known concepts."""

from kb_core.build.concepts import norm
from kb_core.build.tokenize import tokens
from kb_core.domains import informative
from kb_core.retrieval import aliases, context
from kb_core.retrieval.core import ApiError, enum, integer, reject_unknown
from kb_core.retrieval.tracing import traced

PARAMS = {"term", "lang_hint", "limit"}
NEARBY = 3


def _validate(p: dict) -> dict:
    reject_unknown(p, PARAMS)
    term = p.get("term")
    if not isinstance(term, str) or not 1 <= len(term.strip()) <= 100:
        raise ApiError("INVALID_PARAM", "term must be a string of 1-100 characters", param="term", allowed="1-100 chars")
    return {"term": term.strip(), "lang_hint": enum(p, "lang_hint", ["any", "en", "zh"], "any"),
            "limit": integer(p, "limit", 5, 1, 20)}


def run_resolve(params: dict):
    from kb_core.retrieval.facts import availability, derivation

    ctx = context.current()
    v = _validate(params)
    key = norm(v["term"])
    args = {"term": v["term"], "norm": key, "lang": v["lang_hint"], "limit": v["limit"],
            "prefix": key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"}
    scope = {"filters_applied": {"lang_hint": v["lang_hint"], "limit": v["limit"]}, "filters_ignored": [],
             "term_norm": key, "lang_fallback": False}
    detail = {"match_order": ["exact", "alias", "prefix"]}
    if not key:
        return [], scope, [_unknown(v["term"])], False, detail
    hits: list[dict] = []
    for lang in dict.fromkeys([v["lang_hint"], "any"]):   # lang_hint is a preference: fall back to all languages
        args["lang"] = lang
        hits = ctx.pg_rows("K1_alias_exact", args) or ctx.pg_rows("K2_alias_prefix", args)
        if hits:
            scope["lang_fallback"] = lang != v["lang_hint"]
            break
    order = list(dict.fromkeys(h["concept_id"] for h in hits))[:v["limit"]]
    match: dict[str, str] = {}
    for h in hits:
        match.setdefault(h["concept_id"], h["match"])
    cards = {r["concept_id"]: r for r in ctx.pg_rows("K3_concept_cards", {"ids": order})}
    edges = ctx.pg_rows("K4_concept_edges", {"ids": order})
    years = availability(order)
    results = []
    for cid in order:
        c = cards[cid]

        def rel(relation, side, other):
            return sorted(e[other] for e in edges if e["relation"] == relation and e[side] == cid)

        results.append({
            "tier": "link", "status": "linked", "concept_id": cid, "labels": {"en": c["name_en"], "zh": c["name_zh"]},
            "aliases": {"en": c["aliases_en"], "zh": c["aliases_zh"]}, "value_type": c["value_type"],
            "aggregation": c["aggregation"], "parents": rel("broader", "src_concept_id", "dst_concept_id"),
            "children": rel("broader", "dst_concept_id", "src_concept_id"),
            "variants": sorted(set(rel("variant_of", "src_concept_id", "dst_concept_id")
                                   + rel("variant_of", "dst_concept_id", "src_concept_id"))),
            "components": rel("component_of", "dst_concept_id", "src_concept_id"),
            "match": match[cid], "node_count": _visible_node_count(cid, int(c["node_count"])),
            "has_facts": bool(years[cid]),
            "available_periods": years[cid], "derivation": derivation(cid)})
    return results, scope, ([] if results else [_unknown(v["term"])]), False, detail


def resolve_concept(params: dict, source: str = "http", session_id: str | None = None,
                    subject: str | None = None) -> dict:
    return traced("resolve_concept", params, run_resolve, source=source, session_id=session_id, subject=subject)


def nearby(term: str, limit: int = NEARBY) -> list[dict]:
    """Similar known concepts for an unrecognised term: contained (the term holds a whole wording) before partial."""
    from kb_core.retrieval.facts import availability, derivation

    domain = context.current().settings.domain
    have = set(tokens(term.replace("_", " "), domain))
    want = {t for t in have if informative(t, domain)}
    if not want:
        return []
    names = aliases.concept_spec(domain)
    score = {}
    for cid, reported, recognise in aliases.table(domain)[1]:
        spellings = [set(tokens(s, domain)) for s in (*reported, *recognise, cid.replace("_", " "))]
        hit = max((len(want & t) for t in spellings), default=0)
        if hit:
            score[cid] = (any(t and t <= have and t & want for t in spellings), hit)
    years = availability(list(score))
    ranked = sorted(score, key=lambda c: (not score[c][0], -score[c][1], c))[:limit]
    return [{"concept_id": c, "labels": names[c]["name"], "match": "contained" if score[c][0] else "partial",
             "has_facts": bool(years[c]), "available_periods": years[c], "derivation": derivation(c)} for c in ranked]


def next_for_unknown(term: str, candidates: list[dict]) -> list[dict]:
    from kb_core.retrieval.facts import next_for_no_facts

    out = []
    for c in (c for c in candidates if c["match"] == "contained"):
        if c["has_facts"]:
            out.append({"tool": "get_metric_series", "params": {"concept_id": c["concept_id"]},
                        "why": f"similar known metric \"{c['labels']['en']}\" has facts "
                               f"({c['available_periods'][0]}-{c['available_periods'][-1]})"})
        else:
            out += [n for n in next_for_no_facts(c["concept_id"], c["labels"]["en"], None) if n["tool"] == "read"][:2]
    return out + [{"tool": "search", "params": {"query": term}, "why": "search the source text by words"}]


def _unknown(term: str) -> dict:
    cands = nearby(term)
    return {"code": "concept_unknown", "term": term, "candidates": cands, "next": next_for_unknown(term, cands),
            "detail": "the concept table has no such wording (no exact or prefix match). contained: the term holds one "
                      "of the candidate's wordings; partial: only some tokens are shared; or search by words"}


def _visible_node_count(concept_id: str, stored: int) -> int:
    """Nodes tagged with the concept that the current subject may see (round 2 W3: counts never include hidden
    content). Full access keeps the stored count."""
    from kb_core.access import scope

    if not scope.restricted():
        return stored
    cat = context.current().catalog
    n = 0
    for doc_id in cat.visible_docs():
        tree = cat.primary(doc_id)
        n += sum(1 for nid, node in tree.nodes.items()
                 if any(t["concept_id"] == concept_id for t in cat.node_concepts.get(nid, []))
                 and scope.visible(node.get("access")))
    return n
