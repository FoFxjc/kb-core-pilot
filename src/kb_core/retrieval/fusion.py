"""Fusion (port of kb service/search.py _fuse / cap_links / _order; design §5, config/ranking.yaml).

Gated routes keep hits at or above the coverage threshold (ranks recomputed among the kept); a page hit maps to the
first deepest covering node that starts on that page, else the first in reading order (kb-core deviation: kb maps it to
every covering node, which lets one page split into several leaf nodes fill the top k; the project owner, 2026-10-27; owner first:
round 2 W1); accept() decides whether a hit is taken and may add fields; scored routes add RRF 1/(k+rank)
with k = 60; layer: a route with a tier fixes it (concept -> link), else a structural hit whose title holds an
informative query token -> structure, else text. Fusion reads route attributes only.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from kb_core.retrieval.routes import EVIDENCE_ROUTES, RecallRoute

RRF_K = 60
TIER_ORDER = {"fact": 0, "link": 1, "structure": 2, "text": 3}


@dataclass
class Candidate:
    node_id: str
    doc_id: str
    fields: dict[str, int] = field(default_factory=dict)
    pages: list[dict] = field(default_factory=list)
    concepts: list[dict] = field(default_factory=list)
    coverage: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    title_terms: list[str] = field(default_factory=list)
    tier: str = "text"
    group: str | None = None
    demoted_link: list[dict] | None = None


def rrf(fields: dict[str, int], scored: set[str]) -> float:
    return round(sum(1 / (RRF_K + rank) for f, rank in fields.items() if f in scored), 6)


def owner_first(covering: list[str], start_page: dict[str, int], page_no: int) -> list[str]:
    """Covering nodes of a page, those starting on it first (stable): a page hit belongs to the section that starts on
    the page rather than to one continuing from earlier pages (round 2 W1)."""
    return sorted(covering, key=lambda n: start_page.get(n) != page_no)


def base_tier(c: Candidate, title_informative: Callable[[Candidate], bool],
              routes: tuple[RecallRoute, ...] = EVIDENCE_ROUTES) -> str:
    structural = any(r.structural and r.name in c.fields for r in routes)
    return "structure" if structural and title_informative(c) else "text"


def fuse(hits: dict[str, list[tuple]], *, gate: Callable[[str, str, dict], float], threshold: float,
         title_informative: Callable[[Candidate], bool], page_nodes: Callable[[str, int], list[str]],
         accept: Callable[[RecallRoute, str], dict | None] | None = None,
         routes: tuple[RecallRoute, ...] = EVIDENCE_ROUTES) -> tuple[dict[str, Candidate], dict[str, list]]:
    cand: dict[str, Candidate] = {}
    dropped: dict[str, list] = {}

    def add(node_id: str, doc_id: str, name: str, rank: int, page: dict | None = None, extra: dict | None = None):
        c = cand.setdefault(node_id, Candidate(node_id, doc_id))
        if name not in c.fields or rank < c.fields[name]:
            c.fields[name] = rank
        if page is not None:
            c.pages.append(page)
        if extra and "concepts" in extra:
            c.concepts = extra["concepts"]

    for route in routes:
        route_hits = hits.get(route.name) or []
        if route.unit == "page":
            for rank, ((doc_id, page_no), _, row) in enumerate(route_hits, 1):
                for node_id in page_nodes(doc_id, page_no)[:1]:   # one node per page (kb: every covering node)
                    add(node_id, doc_id, route.name, rank, row)
            continue
        rank = 0
        for node_id, _, row in route_hits:
            if route.gated:
                cov = gate(route.name, node_id, row)
                cand_cov = cov
                if cov < threshold:
                    dropped.setdefault(route.name, []).append([node_id, cov])
                    continue
            extra = accept(route, node_id) if accept else route.accept(node_id, None)
            if extra is None:
                if not route.gated:
                    rank += 1          # a rejected hit still takes its rank
                continue
            rank += 1
            add(node_id, row["doc_id"], route.name, rank, extra=extra)
            if route.gated:
                cand[node_id].coverage[route.name] = cand_cov
    scored = {r.name for r in routes if r.scored}
    tiered = {r.name: r.tier for r in routes if r.tier}
    for c in cand.values():
        c.score = rrf(c.fields, scored)
        tier = next((t for f, t in tiered.items() if f in c.fields), None)
        c.tier = tier or base_tier(c, title_informative, routes)
    return cand, dropped


def order_key(c: Candidate, source_rank: Callable[[Candidate], int]):
    """Layer first; links by tag confidence, then RRF of the other routes, then source_rank, then node_id (kb D39)."""
    if c.tier == "link":
        return (TIER_ORDER["link"], -max(t["confidence"] for t in c.concepts), -c.score, source_rank(c), c.node_id)
    return (TIER_ORDER[c.tier], 0, 0, -c.score, c.node_id)


def cap_links(cands: list[Candidate], cap: int, key, title_informative,
              routes: tuple[RecallRoute, ...] = EVIDENCE_ROUTES) -> list[Candidate]:
    """Keep the first `cap` link results per group; demote the rest to their own layer (concept fields removed,
    original tags kept in demoted_link). A node that only came from the concept route is dropped."""
    seen: dict = {}
    drop = set()
    for c in sorted(cands, key=key):
        if c.tier != "link":
            continue
        seen[c.group] = seen.get(c.group, 0) + 1
        if seen[c.group] > cap:
            c.demoted_link, c.concepts = c.concepts, []
            for r in routes:
                if r.tier == "link":
                    c.fields.pop(r.name, None)
            if not c.fields:
                drop.add(id(c))
            c.tier = base_tier(c, title_informative, routes)
    return [c for c in cands if id(c) not in drop]
