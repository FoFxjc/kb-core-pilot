"""Chunks written to Postgres (design §3 build): tree nodes, pages, intake regions (paragraph level) and tables.

Ported from kb pipeline/build.py: a node's summary is its title plus the 300 characters after the title on its
start page; each page lists the deepest primary nodes covering it (search maps page hits to those nodes).
"""

import re

from kb_core.build.tokenize import to_field
from kb_core.build.tree import TreeNode
from kb_core.build.view import DocView

SUMMARY_CHARS = 300


def summary_of(title: str, page_text: str) -> str:
    text = re.sub(r"\s+", " ", page_text or "").strip()
    first = title.split(";")[0]
    head = re.sub(r"\s+", "", first)[:10]
    pos = 0
    if head:  # find the title in whitespace-free text, then map back to the original position
        compact = text.replace(" ", "")
        k = 0
        for i, ch in enumerate(text):
            if ch.isspace():
                continue
            if compact[k:k + len(head)] == head:
                pos = i + len(first)
                break
            k += 1
    body = text[pos:pos + SUMMARY_CHARS].strip()
    return f"{title} {body}".strip()


def deepest_covering(nodes: list[TreeNode], page_count: int) -> dict[int, list[str]]:
    children: dict[str | None, list[TreeNode]] = {}
    for n in nodes:
        children.setdefault(n.parent_id, []).append(n)
    out: dict[int, list[str]] = {p: [] for p in range(1, page_count + 1)}

    def visit(parent_id: str | None) -> None:
        for n in children.get(parent_id, []):
            for p in range(n.page_start, n.page_end + 1):
                if p in out and not any(k.page_start <= p <= k.page_end for k in children.get(n.node_id, [])):
                    out[p].append(n.node_id)
            visit(n.node_id)

    visit(None)
    return out


def node_rows(view: DocView, nodes: list[TreeNode], doc: dict, domain: str, tree_source: str) -> list[dict]:
    labels = {p["page_no"]: p.get("page_label") for p in view.pages}
    parents = {n.node_id: n.parent_id for n in nodes}
    rows = []
    for n in nodes:
        ancestors, p = [], n.parent_id
        while p:
            ancestors.insert(0, p)
            p = parents[p]
        summary = summary_of(n.title, view.page(n.page_start)["text"])
        rows.append({
            "doc_id": view.doc_id, "node_id": n.node_id, "parent_id": n.parent_id, "ancestors": ancestors,
            "depth": n.depth, "ord": n.ord, "title": n.title, "title_tok": to_field(n.title, domain),
            "summary": summary, "summary_tok": to_field(summary, domain), "start_page": n.page_start,
            "end_page": n.page_end, "page_label_range": [labels.get(n.page_start), labels.get(n.page_end)],
            "tree_source": tree_source, "origin": n.origin, "is_primary": n.is_primary,
            "section_type": n.section_type, "section_rule": n.section_rule, "fiscal_year": doc["fiscal_year"],
            "lang": doc["lang"], "issuer": doc["issuer_id"], "region_ids": n.region_ids})
    return rows


def page_rows(view: DocView, covering: dict[int, list[str]], doc: dict, domain: str, label_source: str) -> list[dict]:
    return [{"doc_id": view.doc_id, "page_no": p["page_no"], "page_label": p.get("page_label"),
             "page_label_source": label_source, "kind": p.get("kind"), "excluded": p.get("excluded", False),
             "width": p.get("width"), "height": p.get("height"), "fiscal_year": doc["fiscal_year"],
             "lang": doc["lang"], "issuer": doc["issuer_id"], "text": p.get("text"),
             "text_tok": to_field(p.get("text") or "", domain), "covering_node_ids": covering.get(p["page_no"], [])}
            for p in view.pages]


def _owner(region: dict, owners: dict[str, str], covering: dict[int, list[str]]) -> str | None:
    return owners.get(region["region_id"]) or next(iter(covering.get(region["page_no"], [])), None)


def region_rows(view: DocView, nodes: list[TreeNode], covering: dict[int, list[str]]) -> list[dict]:
    owners = {rid: n.node_id for n in nodes for rid in n.region_ids}
    return [{"doc_id": view.doc_id, "region_id": r["region_id"], "page_no": r["page_no"], "bbox": r["bbox"],
             "type": r["type"], "subtype": r.get("subtype"), "layer": r["layer"], "reading_order": r["reading_order"],
             "text": r.get("text"), "font": r.get("font"), "status": r["status"], "table_id": r.get("table_id"),
             "node_id": _owner(r, owners, covering)} for r in view.regions]


def table_rows(view: DocView, tables: list[dict], covering: dict[int, list[str]]) -> list[dict]:
    return [{"doc_id": view.doc_id, "table_id": t["table_id"], "region_id": t["region_id"],
             "node_id": next(iter(covering.get(t["page_no"], [])), None), "page_start": t["page_no"],
             "page_end": t["page_no"], "bbox": t["bbox"], "n_rows": t["n_rows"], "n_cols": t["n_cols"],
             "caption": None, "unit_hint": None, "markdown": t.get("markdown"), "extract_method": t.get("extract_method"),
             "table_kind": None, "cells": t["cells"], "parsed": None, "continued_hint": t.get("continued_hint")}
            for t in tables]
