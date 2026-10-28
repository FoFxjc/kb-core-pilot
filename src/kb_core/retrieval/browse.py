"""browse: view the table of contents (port of kb service/browse.py; api-contract §5.2). Reads the catalog only."""

from kb_core.access import scope as access_scope
from kb_core.retrieval import context
from kb_core.retrieval.core import ApiError, estimate_tokens, integer, reject_unknown
from kb_core.retrieval.tracing import traced

PARAMS = {"doc_id", "node_id", "depth", "tree_source"}
BUDGET = 10000


def _entries(tree, start: list[str], depth: int) -> list[dict]:
    """Outline entries; nodes the subject may not see (and everything under them) are left out, and child counts
    count visible children only, so nothing hints at hidden sections (round 2 W3)."""
    out = []

    def kids(nid):
        seen = [k for k in tree.children.get(nid, []) if access_scope.visible(tree.nodes[k].get("access"))]
        access_scope.note_filtered(len(tree.children.get(nid, [])) - len(seen))
        return seen

    def visit(nid, level):
        n = tree.nodes[nid]
        out.append({"tier": "structure", "node_id": nid, "parent_id": n["parent_id"], "depth": n["depth"],
                    "ord": n["ord"], "title": n["title"], "section_type": n["section_type"],
                    "page_range": [n["start_page"], n["end_page"]], "page_label_range": n["page_label_range"],
                    "child_count": len(kids(nid)), "parallel_node_id": None})
        if level < depth:
            for k in kids(nid):
                visit(k, level + 1)

    for nid in start:
        if access_scope.visible(tree.nodes[nid].get("access")):
            visit(nid, 1)
    return out


def run_browse(params: dict):
    cat = context.current().catalog
    reject_unknown(params, PARAMS)
    doc_id = params.get("doc_id")
    if not isinstance(doc_id, str) or doc_id not in cat.visible_docs():
        raise ApiError("UNKNOWN_DOC", f"unknown doc_id: {doc_id!r}", candidates=sorted(cat.visible_docs()))
    depth = integer(params, "depth", 2, 1, 6)
    primary = cat.docs[doc_id]["primary_tree_source"]
    tree_source = params.get("tree_source") or primary
    if tree_source != primary:
        raise ApiError("LAYER_UNAVAILABLE", f"{doc_id} has no {tree_source} tree", available_layers=[primary])
    tree = cat.primary(doc_id)
    node_id = params.get("node_id")
    if node_id is not None and (node_id not in tree.nodes or not access_scope.visible(tree.nodes[node_id].get("access"))):
        raise ApiError("UNKNOWN_NODE", f"node {node_id!r} not in {doc_id}")
    start = [node_id] if node_id else tree.children.get(None, [])
    gaps, truncated, d = [], False, depth
    results = _entries(tree, start, d)
    while d > 1 and estimate_tokens(results) > BUDGET:
        d -= 1
        results = _entries(tree, start, d)
        truncated = True
    while estimate_tokens(results) > BUDGET:
        results.pop()
        truncated = True
    if truncated:
        gaps.append({"code": "truncated", "detail": f"exceeds the {BUDGET} token budget; depth reduced from {depth} to {d}",
                     "depth_requested": depth, "depth_returned": d})
    acc = cat.tree_accuracy(doc_id)
    if acc is None or acc < 0.85:
        gaps.append({"code": "tree_quality_low", "doc_id": doc_id, "tree_sample_accuracy": acc,
                     "detail": "primary tree spot-check accuracy is below 85% or not yet checked"})
    doc = cat.docs[doc_id]
    scope = {"filters_applied": {"doc_id": doc_id, "node_id": node_id, "depth": depth, "tree_source": tree_source},
             "filters_ignored": [], "doc_count": 1, "docs": [cat.doc_summary(doc_id)],
             "available_periods": cat.available_periods(), "tree_source": tree_source, "is_primary_tree": True,
             "tree_sample_accuracy": acc,
             "document": {"doc_id": doc_id, "issuer_id": doc["issuer_id"], "lang": doc["lang"],
                          "fiscal_year": doc["fiscal_year"], "page_count": doc["page_count"],
                          "page_label_source": doc["page_label_source"], "source_url": doc["source_url"],
                          "completeness": doc["completeness"]}}
    return results, scope, gaps, truncated, {}


def browse(params: dict, source: str = "http", session_id: str | None = None,
           subject: str | None = None) -> dict:
    return traced("browse", params, run_browse, source=source, session_id=session_id, subject=subject)


def render_text(results: list[dict]) -> str:
    """MCP text: `[last 4 of node_id] title (physical pages s-e / printed pages s-e) {section_type}` per line."""
    if not results:
        return "(empty)"
    base = min(r["depth"] for r in results)
    lines = []
    for r in results:
        labels = r["page_label_range"] or [None, None]
        lines.append(f"{'  ' * (r['depth'] - base)}[{r['node_id'][-4:]}] {r['title']} "
                     f"(physical pages {r['page_range'][0]}-{r['page_range'][1]} / printed pages {labels[0]}-{labels[1]}) "
                     f"{{{r['section_type'] or '-'}}}")
    return "\n".join(lines)
