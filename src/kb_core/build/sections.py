"""Section classification (design §3 build; port of kb profiles/annual_report/sections.py).

Contents entries (origins toc / subtoc / toc_preface / subtoc_intro) take the first matching rule of the profile's
sections.yaml; their descendants inherit it. A contents group takes a type only when all its entries agree.
"""

import re

from kb_core.build.tree import Node

ENTRY_ORIGINS = {"toc", "subtoc", "toc_preface", "subtoc_intro"}


def _rules(vocab: dict) -> list[dict]:
    return [dict(r, _title=re.compile(r["title"], re.I) if r.get("title") else None,
                 _group=re.compile(r["group"], re.I) if r.get("group") else None)
            for r in vocab.get("rules", [])]


def match(title: str, origin: str, group: str | None, rules: list[dict]) -> tuple[str, str] | None:
    for r in rules:
        if r.get("origin") and origin not in r["origin"]:
            continue
        if r["_group"] and not (group and r["_group"].search(group)):
            continue
        if r["_title"] and not r["_title"].search(title.strip()):
            continue
        if not (r.get("origin") or r["_group"] or r["_title"]):
            continue
        return r["section_type"], r["id"]
    return None


def assign(nodes: list[Node], vocab: dict) -> None:
    """Set section_type / section_rule on every node of the tree in place."""
    rules = _rules(vocab)
    types = vocab.get("section_types", {})
    for r in rules:
        assert r["section_type"] in types, f"rule {r['id']} uses unknown section_type {r['section_type']}"

    def visit(ns: list[Node], group: str | None, inherited: tuple[str, str] | None) -> None:
        for n in ns:
            if inherited:
                n.section_type, n.section_rule = inherited
                visit(n.nodes, group, inherited)
            elif n.origin == "toc_group":
                visit(n.nodes, n.title, None)
                kinds = {c.section_type for c in n.nodes}
                n.section_type = kinds.pop() if len(kinds) == 1 else None
                ids = {c.section_rule for c in n.nodes}
                n.section_rule = (ids.pop() if len(ids) == 1 else "GROUP") if n.section_type else None
            elif n.origin in ENTRY_ORIGINS:
                hit = match(n.title, n.origin, group, rules)
                n.section_type, n.section_rule = hit or (None, None)
                visit(n.nodes, group, hit)
            else:
                n.section_type, n.section_rule = None, None
                visit(n.nodes, group, None)

    visit(nodes, None, None)
