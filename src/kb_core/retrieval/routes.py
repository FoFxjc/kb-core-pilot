"""Recall routes (port of kb service/routes.py; design §5). Every route implements the same interface and fusion
reads only these attributes, never route names. Five routes: title, summary and body BM25 (ES), concept (ES,
unscored, link layer) and fact (Postgres, placed before evidence).

Attributes: name (key in candidate fields and traces), unit (node | page: page hits map to the deepest covering
node), scored (takes part in RRF), gated (coverage threshold), tier (a hit fixes the layer), structural (a title hit
with an informative token makes the node structure), layer (evidence | fact).
"""

from dataclasses import dataclass, field

from kb_core.access import scope
from kb_core.access.routes import es_access_filter
from kb_core.retrieval import context

POOL = 50
CONCEPT_POOL = 200


@dataclass
class RecallContext:
    match: str
    docs: list[str]
    section_types: list[str] | None = None
    concepts: list[str] = field(default_factory=list)
    queries: dict = field(default_factory=dict)      # template id -> final DSL, for the trace


def es_filters(ctx: RecallContext, by_section: bool, primary: bool) -> list[dict]:
    f: list[dict] = [{"terms": {"doc_id": ctx.docs}}]
    if primary:
        f.append({"term": {"is_primary": True}})
    if by_section and ctx.section_types:
        f.append({"terms": {"section_type": ctx.section_types}})
    return f + es_access_filter(scope.terms())       # inside every route: hidden content is never recalled


def _ranked(rows: list[tuple]) -> list[tuple]:
    return sorted(rows, key=lambda x: (-x[1], str(x[0])))


class RecallRoute:
    name: str
    trace_name: str | None = None
    unit = "node"
    scored = True
    gated = False
    tier: str | None = None
    structural = False
    layer = "evidence"

    @property
    def trace_key(self) -> str:
        return self.trace_name or self.name

    def recall(self, ctx: RecallContext) -> list[tuple]:
        raise NotImplementedError

    def hay(self, doc_id: str, node_id: str) -> list[str]:
        raise NotImplementedError

    def accept(self, node_id: str, ctx: RecallContext) -> dict | None:
        return {}


class Bm25NodeRoute(RecallRoute):
    gated = True

    def __init__(self, name: str, template: str, hay_kind: str):
        self.name, self.template, self.hay_kind = name, template, hay_kind

    def recall(self, ctx: RecallContext) -> list[tuple]:
        hits = context.current().es_search("node", self.template, {
            "size": POOL, "match": ctx.match, "filters": es_filters(ctx, True, True)}, ctx.queries)
        return _ranked([(h["_source"]["node_id"], float(h["_score"]), dict(h["_source"], s=h["_score"])) for h in hits])

    def hay(self, doc_id: str, node_id: str) -> list[str]:
        cat = context.current().catalog
        return cat.title_tokens(doc_id, node_id) if self.hay_kind == "title" else cat.summary_tokens(doc_id, node_id)


class TitleRoute(Bm25NodeRoute):
    structural = True

    def __init__(self):
        super().__init__("title_tok", "S1_node_title_bm25", "title")


class SummaryRoute(Bm25NodeRoute):
    def __init__(self):
        super().__init__("summary_tok", "S2_node_summary_bm25", "summary")


class PageTextRoute(RecallRoute):
    name = "page_text_tok"
    unit = "page"

    def recall(self, ctx: RecallContext) -> list[tuple]:
        # pages are not filtered by section; fusion filters the nodes the pages map to
        hits = context.current().es_search("page", "S3_page_text_bm25", {
            "size": POOL, "match": ctx.match, "filters": es_filters(ctx, False, False)}, ctx.queries)
        return _ranked([((h["_source"]["doc_id"], int(h["_source"]["page_no"])), float(h["_score"]),
                         dict(h["_source"], s=h["_score"])) for h in hits])


class ConceptRoute(RecallRoute):
    """S6: primary-tree nodes tagged with a query concept; unscored, no gate, link layer."""
    name = "concept_tok"
    trace_name = "concept"
    scored = False
    tier = "link"

    def recall(self, ctx: RecallContext) -> list[tuple]:
        if not ctx.concepts:
            return []
        hits = context.current().es_search("node", "S6_node_concept_match", {
            "size": CONCEPT_POOL, "match": " ".join(ctx.concepts), "filters": es_filters(ctx, True, True)},
            ctx.queries)
        return [(h["_source"]["node_id"], 0.0, dict(h["_source"], s=0.0)) for h in hits]

    def accept(self, node_id: str, ctx: RecallContext) -> dict | None:
        wanted = set(ctx.concepts)
        tags = [t for t in context.current().catalog.node_concepts.get(node_id, []) if t["concept_id"] in wanted]
        return {"concepts": tags} if tags else None


@dataclass
class FactContext:
    concepts: list[str]
    fiscal_years: list[int] | None
    group_by: str
    docs: list[str]
    include_snippet: bool
    section_types: list[str] | None


class FactRoute(RecallRoute):
    """Fact layer: one result per written concept and year, before evidence, outside the limit (kb D40).
    Not used when filtering by section type. Facts arrive with Task 20; until then it returns nothing."""
    name = "fact"
    layer = "fact"
    scored = False

    def recall(self, ctx: FactContext) -> list[dict]:
        if not ctx.concepts or ctx.section_types:
            return []
        from kb_core.retrieval import facts

        return facts.fact_results(ctx.concepts, ctx.fiscal_years, ctx.group_by, ctx.docs, ctx.include_snippet)


EVIDENCE_ROUTES: tuple[RecallRoute, ...] = (TitleRoute(), SummaryRoute(), PageTextRoute(), ConceptRoute())
FACT_ROUTE = FactRoute()
