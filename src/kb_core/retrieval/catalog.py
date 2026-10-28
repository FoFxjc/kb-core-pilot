"""Catalog cache (port of kb service/cache.py; api-contract §6.1): document metadata, each document's primary tree,
token caches, page document frequencies and concept tags, loaded from Postgres. browse, local outlines and
page-to-node mapping read only the cache. Call refresh() after documents are rebuilt.
"""

import threading
from collections import Counter
from dataclasses import dataclass, field

from kb_core.build.tokenize import tokens


@dataclass
class Tree:
    doc_id: str
    tree_source: str
    nodes: dict[str, dict]
    children: dict[str | None, list[str]] = field(default_factory=dict)

    def __post_init__(self):
        for nid in sorted(self.nodes, key=lambda k: (self.nodes[k]["ord"], k)):
            self.children.setdefault(self.nodes[nid]["parent_id"], []).append(nid)

    def path(self, node_id: str) -> list[str]:
        out, cur = [], self.nodes.get(node_id)
        while cur:
            out.append(cur["title"])
            cur = self.nodes.get(cur["parent_id"]) if cur["parent_id"] else None
        return out[::-1]

    def deepest_covering(self, page_no: int) -> list[str]:
        out = []

        def visit(parent):
            for nid in self.children.get(parent, []):
                n = self.nodes[nid]
                if n["start_page"] <= page_no <= n["end_page"]:
                    if not any(self.nodes[k]["start_page"] <= page_no <= self.nodes[k]["end_page"]
                               for k in self.children.get(nid, [])):
                        out.append(nid)
                    visit(nid)
        visit(None)
        return out

    def local_outline(self, node_id: str, max_lines: int = 12) -> list[str]:
        """The node among its siblings, under its parent; nodes the current subject may not see are left out."""
        from kb_core.access import scope

        n = self.nodes[node_id]
        siblings = [s for s in self.children.get(n["parent_id"], [])
                    if s == node_id or scope.visible(self.nodes[s].get("access"))]
        parent = self.nodes.get(n["parent_id"]) if n["parent_id"] else None
        lines = [parent["title"]] if parent is not None and scope.visible(parent.get("access")) else []
        budget = max_lines - len(lines)
        i = siblings.index(node_id)
        lo = max(0, min(i - budget // 2, len(siblings) - budget))
        for sid in siblings[lo:lo + budget]:
            lines.append(("> " if sid == node_id else "  ") + self.nodes[sid]["title"])
        return lines


class Catalog:
    def __init__(self, ctx):
        self.ctx = ctx
        self._lock = threading.Lock()
        self.docs: dict[str, dict] = {}
        self.trees: dict[str, Tree] = {}
        self.coverage: dict[str, dict] = {}
        self.node_concepts: dict[str, list[dict]] = {}
        self._title_tok: dict = {}
        self._summary_tok: dict = {}
        self._df: tuple[int, Counter] | None = None

    def refresh(self) -> None:
        docs = {r["doc_id"]: r for r in self.ctx.pg_rows("G0_documents")}
        groups: dict[tuple, str] = {}
        for d in docs.values():  # language editions of one issuer, type and period form a parallel group
            key = (d["issuer_id"], d["doc_type"], str(d["period_end"]))
            d["parallel_group_id"] = groups.setdefault(key, "|".join(key))
        nodes: dict[str, dict[str, dict]] = {}
        for r in self.ctx.pg_rows("G1_tree_nodes"):
            nodes.setdefault(r["doc_id"], {})[r["node_id"]] = r
        trees = {d: Tree(d, docs[d]["primary_tree_source"] or "regions", nodes.get(d, {})) for d in docs}
        node_concepts: dict[str, list[dict]] = {}
        for r in self.ctx.pg_rows("G3_node_concepts"):
            node_concepts.setdefault(r.pop("node_id"), []).append({**r, "confidence": round(float(r["confidence"]), 2)})
        coverage: dict[str, dict] = {}
        for r in self.ctx.pg_rows("G4_coverage"):
            coverage.setdefault(r["scope_id"], {})[r["metric"]] = r["value"]
        with self._lock:
            self.docs, self.trees, self.node_concepts, self.coverage = docs, trees, node_concepts, coverage
            self._title_tok, self._summary_tok, self._df = {}, {}, None

    def primary(self, doc_id: str) -> Tree:
        return self.trees[doc_id]

    def title_tokens(self, doc_id: str, node_id: str) -> list[str]:
        key = (doc_id, node_id)
        if key not in self._title_tok:
            self._title_tok[key] = tokens(self.primary(doc_id).nodes[node_id]["title"], self.ctx.settings.domain)
        return self._title_tok[key]

    def summary_tokens(self, doc_id: str, node_id: str) -> list[str]:
        key = (doc_id, node_id)
        if key not in self._summary_tok:
            self._summary_tok[key] = tokens(self.primary(doc_id).nodes[node_id]["summary"] or "",
                                            self.ctx.settings.domain)
        return self._summary_tok[key]

    def page_df(self) -> tuple[int, Counter]:
        """(number of pages N, token -> pages containing it) over every built page: the coverage gate's IDF."""
        if self._df is None:
            df: Counter = Counter()
            rows = self.ctx.pg_rows("G2_page_tokens")
            for r in rows:
                df.update(set((r["text_tok"] or "").split()))
            self._df = (len(rows), df)
        return self._df

    def visible_docs(self) -> dict[str, dict]:
        """The documents the current subject may see (round 2 W3); everything else behaves as if it did not exist."""
        from kb_core.access import scope

        return {d: m for d, m in self.docs.items() if scope.visible(m.get("access"))}

    def parallel_docs(self, doc_id: str) -> list[str]:
        group = self.docs[doc_id]["parallel_group_id"]
        return sorted(d for d, m in self.visible_docs().items() if m["parallel_group_id"] == group and d != doc_id)

    def tree_accuracy(self, doc_id: str) -> float | None:
        v = self.coverage.get(doc_id, {}).get("tree_sample_accuracy")
        return v["value"] if v else None

    def available_periods(self) -> list[int]:
        return sorted({d["fiscal_year"] for d in self.visible_docs().values()})

    def doc_summary(self, doc_id: str) -> dict:
        d = self.docs[doc_id]
        full = (d["completeness"] or {}).get("full", True)
        return {"doc_id": doc_id, "lang": d["lang"], "fiscal_year": d["fiscal_year"],
                "completeness": "full" if full else "partial"}

    def source(self, doc_id: str, node: dict | None = None, page_range: list[int] | None = None,
               page_labels: list | None = None) -> dict:
        d = self.docs[doc_id]
        out = {"doc_id": doc_id, "lang": d["lang"], "fiscal_year": d["fiscal_year"]}
        if node:
            out.update(node_id=node["node_id"], title_path=self.primary(doc_id).path(node["node_id"]),
                       page_range=[node["start_page"], node["end_page"]], page_label_range=node["page_label_range"])
        else:
            out.update(page_range=page_range, page_label_range=page_labels)
        out["source_url"] = d["source_url"]
        return out
