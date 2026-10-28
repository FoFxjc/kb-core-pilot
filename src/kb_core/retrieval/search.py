"""search: find (port of kb service/search.py; api-contract §5.1, §6). Deterministic: the same request always gets
the same result except trace_id. Storage is swapped (ES for BM25 routes and hit counts, Postgres catalog for trees);
the steps, ranking rules and gaps are kb's.
"""

import re
from functools import cache

import yaml

from kb_core import profiles
from kb_core.domains import informative, low_info
from kb_core.build.tokenize import tokens
from kb_core.paths import data_dir
from kb_core.access import scope as access_scope
from kb_core.access.routes import es_access_filter
from kb_core.retrieval import aliases, context
from kb_core.retrieval.core import (ApiError, boolean, enum, estimate_tokens, ignored_gap, int_list, integer,
                                    reject_unknown, string_list)
from kb_core.retrieval.coverage import coverage, coverage_units
from kb_core.retrieval.fusion import Candidate, cap_links, fuse, order_key, owner_first
from kb_core.retrieval.routes import EVIDENCE_ROUTES, FACT_ROUTE, FactContext, RecallContext, es_filters
from kb_core.retrieval.tracing import traced

PARAMS = {"query", "lang", "fiscal_years", "doc_ids", "section_types", "group_by", "per_group", "limit",
          "include_snippet", "entity_scope", "concepts", "doc_type"}
GROUP_BY = ["none", "fiscal_year", "doc_id", "lang", "section_type"]
BUDGET = 8000
SNIPPET = 300
UNCLASSIFIED = "unclassified"
HIT_PAGES = 10000


@cache
def _ranking_spec() -> dict:
    spec = yaml.load((data_dir("config") / "ranking.yaml").read_text(), Loader=yaml.BaseLoader)
    return {"version": int(spec["version"]), "threshold": float(spec["coverage_threshold"]),
            "link_per_group": int(spec["link_per_group"])}


def ranking() -> dict:
    """config/ranking.yaml; KB_CORE_COVERAGE_THRESHOLD (evaluation sweeps) overrides the coverage threshold."""
    from kb_core.config import current

    s = current()
    out = dict(_ranking_spec())
    if s is not None and s.coverage_threshold is not None:
        out["threshold"] = s.coverage_threshold
    return out


def _validate(p: dict) -> tuple[dict, list[str], list[dict]]:
    cat = context.current().catalog
    reject_unknown(p, PARAMS)
    q = p.get("query")
    if not isinstance(q, str) or not 1 <= len(q) <= 200:
        raise ApiError("INVALID_PARAM", "query must be a string of 1-200 characters", param="query", allowed="1-200 chars")
    v = {
        "query": q,
        "lang": enum(p, "lang", ["any", "en", "zh"], "any"),
        "fiscal_years": int_list(p, "fiscal_years", 2000, 2100),
        "doc_ids": string_list(p, "doc_ids"),
        "section_types": string_list(p, "section_types"),
        "group_by": enum(p, "group_by", GROUP_BY, "none"),
        "per_group": integer(p, "per_group", 3, 1, 10),
        "limit": integer(p, "limit", 10, 1, 30),
        "include_snippet": boolean(p, "include_snippet", True),
        "doc_type": enum(p, "doc_type", sorted(set(profiles.registered()) | {d["doc_type"] for d in cat.docs.values()}),
                         "annual_report"),
    }
    vocab = list(profiles.section_types())
    for st in v["section_types"] or []:
        if st not in vocab:
            raise ApiError("INVALID_PARAM", f"unknown section_type {st!r}", param="section_types", allowed=vocab)
    ignored, gaps = [], []
    if p.get("entity_scope") is not None:
        enum(p, "entity_scope", ["any", "group", "bank"], "any")
        ignored.append("entity_scope")
        gaps.append(ignored_gap("entity_scope", "nodes carry no entity scope yet"))
    if p.get("concepts") is not None:
        string_list(p, "concepts")
        ignored.append("concepts")
        gaps.append(ignored_gap("concepts", "concepts are recognised from the query text"))
    if v["doc_ids"]:
        visible = cat.visible_docs()       # a hidden document is reported exactly like one that does not exist
        unknown = [d for d in v["doc_ids"] if d not in visible]
        if unknown:
            raise ApiError("UNKNOWN_DOC", f"unknown doc_id(s): {unknown}", candidates=sorted(visible))
    return v, ignored, gaps


def _scope_docs(v: dict) -> list[str]:
    out = []
    for doc_id, d in sorted(context.current().catalog.visible_docs().items()):
        if v["lang"] != "any" and d["lang"] != v["lang"]:
            continue
        if v["fiscal_years"] and d["fiscal_year"] not in v["fiscal_years"]:
            continue
        if v["doc_ids"] and doc_id not in v["doc_ids"]:
            continue
        if d["doc_type"] != v["doc_type"]:
            continue
        out.append(doc_id)
    return out


def _groups(v: dict, docs: list[str]) -> list[tuple[str | None, list[str]]]:
    if v["group_by"] in ("none", "section_type"):
        return [(None, docs)]
    cat = context.current().catalog
    key = {"fiscal_year": lambda d: str(cat.docs[d]["fiscal_year"]), "lang": lambda d: cat.docs[d]["lang"],
           "doc_id": lambda d: d}[v["group_by"]]
    groups: dict[str, list[str]] = {}
    for d in docs:
        groups.setdefault(key(d), []).append(d)
    return sorted(groups.items())


def _snippet(text: str, terms: list[str]) -> str:
    flat = re.sub(r"\s+", " ", text or "").strip()
    low = flat.lower()
    pos = min((low.find(t) for t in terms if low.find(t) >= 0), default=0)
    start = max(0, pos - SNIPPET // 3)
    return flat[start:start + SNIPPET]


def field_order() -> list[str]:
    return [r.name for r in EVIDENCE_ROUTES if r.tier] + [r.name for r in EVIDENCE_ROUTES if not r.tier]


def _source_rank(c: Candidate) -> int:
    st = context.current().catalog.primary(c.doc_id).nodes[c.node_id]["section_type"]
    rank = (profiles.section_types().get(st) or {}).get("source_rank") if st else None
    return int(rank) if rank not in (None, "null") else 99


def _key(c: Candidate):
    return order_key(c, _source_rank)


def _entry(c: Candidate, terms: list[str], include_snippet: bool, domain: str) -> dict:
    cat = context.current().catalog
    tree = cat.primary(c.doc_id)
    node = tree.nodes[c.node_id]
    hay = set(cat.title_tokens(c.doc_id, c.node_id)) | set(tokens(node["summary"] or "", domain))
    for page in c.pages:
        hay |= set((page.get("text_tok") or "").split())
    matched_terms = [t for t in terms if t in hay]
    snippet = None
    if include_snippet:
        best = min(c.pages, key=lambda r: (-float(r["s"]), int(r["page_no"]))) if c.pages else None
        snippet = _snippet(best["text"] if best else (node["summary"] or ""), matched_terms or terms)
    return {
        "tier": c.tier, "status": "linked" if c.tier == "link" else "unlinked", "rank": 0, "score": c.score,
        "node_id": c.node_id, "title": node["title"], "section_type": node["section_type"],
        "matched": {"fields": [f for f in field_order() if f in c.fields], "terms": matched_terms,
                    "concepts": [{k: t[k] for k in ("concept_id", "method", "variant", "confidence")}
                                 for t in c.concepts]},
        "snippet": snippet, "local_outline": tree.local_outline(c.node_id),
        "source": cat.source(c.doc_id, node), "parallel_node_id": None, "group": c.group,
    }


def _hit_counts(match: str, docs_filtered: list[str], doc_ids: list[str] | None, log: dict) -> tuple[dict, dict]:
    ctx = context.current()

    def shape(resp):
        a = resp["aggregations"]
        return {"fiscal_year": dict(sorted((str(b["key"]), b["doc_count"]) for b in a["fiscal_year"]["buckets"])),
                "lang": dict(sorted((b["key"], b["doc_count"]) for b in a["lang"]["buckets"]))}

    if docs_filtered:
        filters = [{"terms": {"doc_id": docs_filtered}}] + es_access_filter(access_scope.terms())
        filtered = shape(ctx.es_raw("page", "S4_hit_counts", {"match": match, "filters": filters}, log))
        if access_scope.restricted():          # audit only: how many matching pages the policy hid
            everything = shape(ctx.es_raw("page", "S4_hit_counts",
                                          {"match": match, "filters": [{"terms": {"doc_id": docs_filtered}}]}, {}))
            access_scope.note_filtered(sum(everything["fiscal_year"].values()) - sum(filtered["fiscal_year"].values()))
        by_section: dict[str, int] = {}
        for h in ctx.es_search("page", "S4b_hit_pages", {"match": match, "filters": filters, "size": HIT_PAGES}, log):
            tree = ctx.catalog.primary(h["_source"]["doc_id"])
            for st in sorted({tree.nodes[n]["section_type"] or UNCLASSIFIED
                              for n in tree.deepest_covering(int(h["_source"]["page_no"]))}):
                by_section[st] = by_section.get(st, 0) + 1
        filtered["section_type"] = dict(sorted(by_section.items()))
    else:
        filtered = {"fiscal_year": {}, "lang": {}, "section_type": {}}
    unfiltered = shape(ctx.es_raw("page", "S5_hit_counts_unfiltered",
                                  {"match": match, "filters": ([{"terms": {"doc_id": doc_ids}}] if doc_ids else [])
                                   + es_access_filter(access_scope.terms())}, log))   # counts over the visible scope only
    return filtered, unfiltered


def _query_concepts(alias_units: list[dict]) -> list[dict]:
    out = [{"concept_id": u["id"], "via": "query", "from": None,
            "variant": " ".join(u["typed"][0]) if u["typed"] else None} for u in alias_units]
    seen = {u["id"] for u in alias_units}
    for u in alias_units:
        for cid in u["concepts"]:
            if cid not in seen:
                seen.add(cid)
                out.append({"concept_id": cid, "via": "broader", "from": u["id"], "variant": None})
    return out


def concept_gaps(concepts: list[str], results: list[dict], enabled: bool) -> list[dict]:
    if not enabled:
        return []
    if not concepts:
        return [{"code": "concept_unknown",
                 "detail": "no metric from the concept table was recognised in the query; searched by tokens only"}]
    if not any(r["tier"] in ("link", "fact") for r in results):
        return [{"code": "unlinked_text_only", "concepts": concepts,
                 "detail": "concepts were recognised, but no section is tagged with them; results are text and title "
                           "hits only"}]
    return []


def _gaps(v: dict, docs: list[str], results: list[dict], hc: dict, hcu: dict) -> list[dict]:
    cat = context.current().catalog
    gaps = []
    if not results and sum(hcu["lang"].values()) > 0:
        gaps.append({"code": "over_filtered", "detail": "0 hits after filtering; there are hits without the year and "
                     "language filters", "hit_counts_unfiltered": hcu,
                     "next": [{"tool": "search", "params": {"query": v["query"]}, "why": "search again without the filters"}]})
    asked = set(profiles.queried_sections(v["query"])) | set(v["section_types"] or [])
    vocab = list(profiles.section_types())
    for d in docs:
        comp = cat.docs[d]["completeness"] or {}
        if comp.get("full", True):
            continue
        lang = cat.docs[d]["lang"]
        missing = sorted(asked - set(comp.get("sections") or []), key=lambda t: vocab.index(t) if t in vocab else 99) \
            if comp.get("sections") is not None else []
        other_lang_hits = sum(n for lng, n in hcu["lang"].items() if lng != lang)
        if missing or v["lang"] == lang or (hc["lang"].get(lang, 0) == 0 and other_lang_hits > 0):
            g = {"code": "section_missing_in_lang", "lang": lang, "doc_id": d, "section_types": missing or None,
                 "detail": comp.get("note")}
            if v["lang"] != "any" and not any(x["code"] == "section_missing_in_lang" for x in gaps):
                other = sorted({cat.docs[p]["lang"] for p in cat.parallel_docs(d)} - {lang})
                if other:
                    params = {"query": v["query"], "lang": other[0],
                              **({"fiscal_years": v["fiscal_years"]} if v["fiscal_years"] else {})}
                    g["next"] = [{"tool": "search", "params": params,
                                  "why": "this language edition is an excerpt; search the full edition in the other language"}]
            gaps.append(g)
    for d in sorted({r["source"]["doc_id"] for r in results}):
        for p in cat.parallel_docs(d):
            if p not in docs:
                gaps.append({"code": "parallel_doc_available", "doc_id": d, "parallel_doc_id": p,
                             "lang": cat.docs[p]["lang"],
                             "detail": "the hit document has an edition in another language that is not in this search's scope"})
        acc = cat.tree_accuracy(d)
        if acc is None or acc < 0.85:
            gaps.append({"code": "tree_quality_low", "doc_id": d, "tree_sample_accuracy": acc,
                         "detail": "primary tree spot-check accuracy is below 85% or not yet checked"})
        if cat.docs[d]["page_label_source"] == "none":
            gaps.append({"code": "page_label_unreliable", "doc_id": d,
                         "detail": "this document has no usable printed page numbers"})
    return gaps


def fit_budget(evidence: list[dict], facts: list[dict], scope: dict, gaps: list[dict]) -> tuple[list, bool, list]:
    """Drop evidence results from the end until the output fits the token budget (facts are outside the budget and
    come first); ranks are renumbered and a `truncated` gap is added when anything was cut."""
    evidence, truncated = list(evidence), False
    lean = [{k: x for k, x in g.items() if k != "next"} for g in gaps]
    while evidence and estimate_tokens({"results": evidence, "scope": scope, "gaps": lean}) > BUDGET:
        evidence.pop()
        truncated = True
    if truncated:
        gaps = gaps + [{"code": "truncated", "detail": f"output exceeds the {BUDGET} token budget; only the first "
                        f"{len(evidence)} evidence results are returned"}]
    results = facts + evidence
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return results, truncated, gaps


def run_search(params: dict) -> tuple[list, dict, list, bool, dict]:
    """(results, scope, gaps, truncated, trace detail)."""
    ctx = context.current()
    cat, domain = ctx.catalog, ctx.settings.domain
    v, ignored, gaps = _validate(params)
    terms, term_sources, alias_units = aliases.expand(v["query"], domain)
    syn_units: list[dict] = []
    if aliases.enabled():                    # word-level synonyms (round 2 W2, class F1)
        from kb_core.domains import query_synonyms

        query_words = [t["term"] for t in term_sources if t["source"] == "query"]
        absorbed = {t for u in alias_units for v in u["typed"] for t in v}
        extra, syn_units = aliases.synonym_units(query_words, query_synonyms(domain), absorbed)
        for t in extra:
            if t not in terms:
                terms.append(t)
                term_sources.append({"term": t, "source": "synonym", "alias_id": None, "variant": None})
    if not terms:
        raise ApiError("INVALID_PARAM", "query contains no searchable terms", param="query",
                       allowed="at least one word containing a letter or digit")
    match = " ".join(terms)
    docs = _scope_docs(v)
    filters_applied = {k: v[k] for k in ("lang", "fiscal_years", "doc_ids", "section_types", "group_by", "per_group",
                                         "limit", "include_snippet", "doc_type")}
    scope = {"filters_applied": filters_applied, "filters_ignored": ignored, "doc_count": len(docs),
             "docs": [cat.doc_summary(d) for d in docs], "query_terms": terms, "query_term_sources": term_sources}
    rk = ranking()
    is_informative = lambda t: informative(t, domain)  # noqa: E731
    units = coverage_units([t["term"] for t in term_sources if t["source"] == "query"], alias_units + syn_units,
                           is_informative)
    query_concepts = _query_concepts(alias_units)
    concepts = [c["concept_id"] for c in query_concepts]
    scope["query_concepts"] = query_concepts
    queries: dict = {}
    detail = {"routes": {}, "low_info_terms_version": low_info(domain)[0], "concepts_version": aliases.table(domain)[0],
              "concept_units": [{"id": u["id"], "concepts": u["concepts"]} for u in alias_units],
              "ranking_version": rk["version"], "coverage_threshold": rk["threshold"],
              "link_per_group": rk["link_per_group"], "informative_terms": [t for t in terms if is_informative(t)],
              "coverage_units": [{"kind": u["kind"], "id": u["id"]} for u in units], "coverage_dropped": {},
              "queries": queries}
    if not docs:
        gaps.append({"code": "empty_scope", "detail": "no documents left after filtering",
                     "available_periods": cat.available_periods()})
        hc, hcu = _hit_counts(match, [], v["doc_ids"], queries)
        scope.update(hit_counts=hc, hit_counts_unfiltered=hcu, available_periods=cat.available_periods())
        return [], scope, gaps, False, detail

    page_df = cat.page_df()

    def title_informative(c: Candidate) -> bool:
        hits = set(terms) & set(cat.title_tokens(c.doc_id, c.node_id))
        c.title_terms = sorted(hits)
        return any(is_informative(t) for t in hits)

    all_cands: list[Candidate] = []
    for group, gdocs in _groups(v, docs):
        rctx = RecallContext(match=match, docs=gdocs, section_types=v["section_types"], concepts=concepts,
                             queries=queries)
        hits = {route.name: route.recall(rctx) for route in EVIDENCE_ROUTES}
        detail["routes"][group or "all"] = {r.trace_key: [str(x[0]) for x in hits[r.name]] for r in EVIDENCE_ROUTES}
        route_by_name = {r.name: r for r in EVIDENCE_ROUTES}

        def page_nodes(doc_id: str, page_no: int) -> list[str]:
            tree = cat.primary(doc_id)
            ids = [n for n in tree.deepest_covering(page_no)
                   if (not v["section_types"] or tree.nodes[n]["section_type"] in v["section_types"])
                   and access_scope.visible(tree.nodes[n].get("access"))]
            return owner_first(ids, {n: tree.nodes[n]["start_page"] for n in ids}, page_no)

        fused, dropped = fuse(
            hits, threshold=rk["threshold"], title_informative=title_informative, page_nodes=page_nodes,
            gate=lambda name, node_id, row: coverage(units, set(route_by_name[name].hay(row["doc_id"], node_id)), page_df),
            accept=lambda route, node_id: route.accept(node_id, rctx))
        detail["coverage_dropped"][group or "all"] = dropped
        # re-check every candidate against the stored labels (Postgres is authoritative; the index may be stale)
        fused = {k: c for k, c in fused.items()
                 if c.doc_id in cat.visible_docs() and access_scope.visible(cat.primary(c.doc_id).nodes[k].get("access"))}
        for c in fused.values():
            title_informative(c)
            c.group = group
            if v["group_by"] == "section_type":
                c.group = cat.primary(c.doc_id).nodes[c.node_id]["section_type"] or UNCLASSIFIED
        all_cands += sorted(fused.values(), key=_key)
    all_cands = cap_links(all_cands, rk["link_per_group"], _key, title_informative)
    all_cands.sort(key=_key)
    if v["group_by"] == "none":
        picked = all_cands[:v["limit"]]
    else:
        picked, seen = [], {}
        for c in all_cands:
            if seen.get(c.group, 0) < v["per_group"]:
                picked.append(c)
                seen[c.group] = seen.get(c.group, 0) + 1
        ids = {c.node_id for c in picked}
        for c in all_cands:
            if len(picked) >= v["limit"]:
                break
            if c.node_id not in ids:
                picked.append(c)
                ids.add(c.node_id)
        picked.sort(key=_key)
    detail["tier_decisions"] = {c.node_id: {"tier": c.tier, "title_terms": c.title_terms, "coverage": c.coverage,
                                            "concepts": c.concepts,
                                            **({"demoted_link": c.demoted_link} if c.demoted_link else {})}
                                for c in picked}
    results = [_entry(c, terms, v["include_snippet"], domain) for c in picked]
    written = [c["concept_id"] for c in query_concepts if c["via"] == "query"]
    fact_rows = FACT_ROUTE.recall(FactContext(concepts=written, fiscal_years=v["fiscal_years"], group_by=v["group_by"],
                                              docs=docs, include_snippet=v["include_snippet"],
                                              section_types=v["section_types"]))
    detail["fact_results"] = [{k: f.get(k) for k in ("concept_id", "fiscal_year", "display", "status", "source")}
                              for f in fact_rows]
    hc, hcu = _hit_counts(match, docs, v["doc_ids"], queries)
    scope.update(hit_counts=hc, hit_counts_unfiltered=hcu, available_periods=cat.available_periods())
    gaps += _gaps(v, docs, results, hc, hcu)
    gaps += concept_gaps(concepts, results + fact_rows, aliases.enabled())
    results, truncated, gaps = fit_budget(results, fact_rows, scope, gaps)
    return results, scope, gaps, truncated, detail


def search(params: dict, source: str = "http", session_id: str | None = None, subject: str | None = None) -> dict:
    return traced("search", params, run_search, source=source, session_id=session_id, subject=subject)


# es_filters is re-exported for the trace view (filters rendered into the final DSL)
__all__ = ["search", "run_search", "es_filters"]
