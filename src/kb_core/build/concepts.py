"""Concept layer (port of kb pipeline/concepts.py; design §3 build): concepts.yaml validation, import into the concept
schema, and node tagging (kb r4 rules: manual > rule_title > rule_row_label > rule_dict).

Tagging inputs: primary-tree nodes, page texts, and tables as interpreted row labels ({node_id, labels}); kb read
Markdown first columns. Section-kind regexes and thresholds come from domains/<domain>/tagging.yaml.
"""

import re
import unicodedata
from functools import cache
from pathlib import Path

import yaml

from kb_core.domains import domain_dir, informative
from kb_core.paths import data_dir
from kb_core.retrieval.aliases import _pattern

VALUE_TYPES = {"amount", "percent", "ratio", "bps", "count"}
AGGREGATIONS = {"flow", "stock", "ratio"}
PERIOD_KINDS = {"duration", "instant"}
RELATIONS = {"broader", "component_of", "variant_of"}
SPELLINGS = (("variants", "manual"), ("query_only", "manual"), ("row_labels", "row_label"))
PRIORITY = ("manual", "rule_title", "rule_row_label", "rule_dict")
DERIVE_OPS = ("/", "-", "+")


class ConceptSpecError(ValueError):
    pass


def parse_derive(expr: str) -> tuple[str, str, str] | None:
    parts = str(expr or "").split()
    if len(parts) == 3 and parts[1] in DERIVE_OPS:
        return parts[0], parts[1], parts[2]
    return None


def norm(s: str) -> str:
    """Alias normalisation: NFKC, lowercase, no whitespace or hyphens."""
    return re.sub(r"[\s\-–—]+", "", unicodedata.normalize("NFKC", s)).lower()


def lang_of(s: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", s) else "en"


def default_paths(domain: str = "banking") -> tuple[Path, Path]:
    return domain_dir(domain) / "concepts.yaml", data_dir("eval") / "heldout_terms.yaml"


def load_spec(path: Path | None = None, heldout: Path | None = None) -> dict:
    """Load and validate concepts.yaml (ids, enums, derive formulas, unique wordings, edges, held-out wordings)."""
    if path is None:
        path, default_heldout = default_paths()
        heldout = heldout or default_heldout
    spec = yaml.safe_load(Path(path).read_text())
    errors = []
    ids = [c["id"] for c in spec["concepts"]]
    for cid in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"duplicate concept id {cid}")
    for c in spec["concepts"]:
        for f, allowed in (("value_type", VALUE_TYPES), ("aggregation", AGGREGATIONS), ("period_kind", PERIOD_KINDS)):
            if c.get(f) not in allowed:
                errors.append(f"{c['id']}: {f}={c.get(f)!r} not in {sorted(allowed)}")
        if "derive" in c:
            d = parse_derive(c["derive"])
            if d is None or d[0] not in ids or d[2] not in ids:
                errors.append(f"{c['id']}: derive={c['derive']!r} must look like \"a / b\" with existing concepts")
    owner: dict[str, tuple[str, str]] = {}
    for c in spec["concepts"]:
        for f, _ in SPELLINGS:
            for s in c.get(f) or ():
                prev = owner.setdefault(norm(s), (c["id"], s))
                if prev[0] != c["id"]:
                    errors.append(f"wording {s!r} ({c['id']}) equals {prev[1]!r} ({prev[0]}) after normalisation")
    for e in spec.get("edges") or ():
        if e.get("relation") not in RELATIONS:
            errors.append(f"edge {e}: relation not in {sorted(RELATIONS)}")
        for end in ("src", "dst"):
            if e.get(end) not in ids:
                errors.append(f"edge {e}: concept {e.get(end)!r} does not exist")
    from kb_core.domains import held_out_wordings

    # every held-out wording: the legacy and old-16 list, the sealed round 2 set (T2.4), and any file passed in
    held = {w: w for w in held_out_wordings()}               # lowercased -> as written (for messages)
    if heldout and Path(heldout).exists():
        held.update({str(t["term"]).lower(): str(t["term"])
                     for t in (yaml.safe_load(Path(heldout).read_text()) or {}).get("terms") or ()})
    if held:
        patterns = [(c["id"], s, _pattern(s)) for c in spec["concepts"] for f, _ in SPELLINGS for s in c.get(f) or ()]
        for term in sorted(held.values()):
            t = {"term": term}
            hits = [f"{s!r} ({cid})" for cid, s, p in patterns if p.search(t["term"].lower())]
            if hits:
                errors.append(f"held-out wording {t['term']!r} is recognised by the concept table: {', '.join(hits)}")
            pre = [f"{s!r} ({cid})" for cid, s, _ in patterns
                   if norm(s).startswith(norm(t["term"])) and norm(s) != norm(t["term"])]
            pre += [f"concept_id {c['id']!r}" for c in spec["concepts"] if c["id"].startswith(t["term"].strip().lower())]
            if pre:
                errors.append(f"held-out wording {t['term']!r} is a prefix of a concept table wording: {', '.join(pre)}")
    if errors:
        raise ConceptSpecError("concepts.yaml validation failed:\n  " + "\n  ".join(errors))
    return spec


def alias_rows(spec: dict) -> list[dict]:
    rows: dict[str, dict] = {}
    for c in spec["concepts"]:
        for f, source in SPELLINGS:
            for s in c.get(f) or ():
                rows.setdefault(norm(s), {"alias_norm": norm(s), "alias": s, "lang": lang_of(s), "concept_id": c["id"],
                                          "source": source, "kind": f})
    return list(rows.values())


@cache
def tagging_rules(domain: str = "banking") -> dict:
    r = yaml.safe_load((domain_dir(domain) / "tagging.yaml").read_text())
    return {**r, "_other": re.compile(r["other_entity"], re.I), "_no_dict": re.compile(r["no_dict"], re.I),
            "_movement": re.compile(r["movement"], re.I),
            "_context": re.compile(r["dict_context_exclude"], re.I) if r.get("dict_context_exclude") else None}


def _spellings(c: dict, fields=("variants", "query_only", "row_labels")) -> list[tuple[str, re.Pattern]]:
    return [(s, _pattern(s)) for f in fields for s in c.get(f) or ()]


def _excluded(c: dict, text: str, span: tuple[int, int]) -> bool:
    return any(xs <= span[0] and span[1] <= xe for x in c.get("exclude") or ()
               for xs, xe in (m.span() for m in _pattern(x).finditer(text)))


def _hits(text: str, concepts_: list[dict]) -> list[tuple[str, str, tuple[int, int]]]:
    """Report-wording hits in lowercased text; excluded wordings do not count; overlapping hits keep the longer."""
    hits = []
    for c in concepts_:
        for s, pat in _spellings(c, ("variants", "row_labels")):
            hits += [(c["id"], s, m.span()) for m in pat.finditer(text) if not _excluded(c, text, m.span())]
    hits.sort(key=lambda h: (-(h[2][1] - h[2][0]), h[2][0], h[0]))
    kept = []
    for h in hits:
        if not any(h[2][0] < k[2][1] and k[2][0] < h[2][1] for k in kept):
            kept.append(h)
    return sorted(kept, key=lambda h: h[2])


def clean_label(label: str) -> str:
    label = re.sub(r"\*\*|<br>", " ", label or "")
    label = re.sub(r"\(\d\)", " ", label)
    return re.sub(r"\s+", " ", label).strip()


def _squash(text: str) -> tuple[str, list[int]]:
    out, pos = [], []
    for i, ch in enumerate(text):
        if not ch.isspace():
            out.append(ch.lower())
            pos.append(i)
    return "".join(out), pos


def own_text(nodes: list[dict], pages: dict[int, str]) -> dict[str, str]:
    """Each node's own body text (kb F1'): the deepest nodes covering a page; a page shared by siblings is split at
    the titles of the nodes starting on it (the page does not count when a title cannot be found)."""
    own: dict[str, list[str]] = {}
    for p, text in sorted(pages.items()):
        text = text or ""
        covering = [n for n in nodes if n["start_page"] <= p <= n["end_page"]]
        if not covering:
            continue
        deepest = max(n["depth"] for n in covering)
        level = sorted((n for n in covering if n["depth"] == deepest), key=lambda n: (n["start_page"], n.get("ord", 0)))
        if len(level) == 1:
            own.setdefault(level[0]["node_id"], []).append(text)
            continue
        flat, pos = _squash(text)
        earlier = [n for n in level if n["start_page"] < p]
        cuts: list | None = []
        for n in (n for n in level if n["start_page"] == p):
            head, _ = _squash((n["title"] or "").split(";")[0])
            at = flat.find(head) if head else -1
            if at < 0:
                cuts = None
                break
            cuts.append((pos[at], n["node_id"]))
        if cuts is None:
            continue
        cuts.sort()
        if len(earlier) == 1 and cuts:
            own.setdefault(earlier[0]["node_id"], []).append(text[:cuts[0][0]])
        for k, (at, node_id) in enumerate(cuts):
            own.setdefault(node_id, []).append(text[at:cuts[k + 1][0] if k + 1 < len(cuts) else len(text)])
    return {k: "\n".join(v) for k, v in own.items()}


def _titles(node: dict, by_id: dict[str, dict]) -> str:
    out, cur = [], node
    while cur is not None:
        out.append(cur["title"] or "")
        cur = by_id.get(cur.get("parent_id"))
    return " / ".join(out)


SENTENCE_END = re.compile(r"[.;](?=\s|$)|[\u3002\uff1b\uff01\uff1f!?]")   # CJK full stop, semicolon, ! and ?


def _sentence_window(text: str, span: tuple[int, int], width: int) -> str:
    """Up to `width` characters either side of a hit, cut at the sentence ends around it ('.' before a space or the
    end, ';' and CJK sentence marks; a decimal point is not an end)."""
    lo, hi = max(0, span[0] - width), min(len(text), span[1] + width)
    ends_before = [m.end() for m in SENTENCE_END.finditer(text, lo, span[0])]
    after = SENTENCE_END.search(text, span[1], hi)
    return text[ends_before[-1] if ends_before else lo:after.start() if after else hi]


def tag_nodes(nodes: list[dict], pages: dict[int, str], tables: list[dict], spec: dict, overrides: dict,
              rules: dict | None = None, domain: str = "banking") -> list[dict]:
    """[{node_id, concept_id, method, variant, confidence}] for the primary-tree nodes of one document."""
    rules = rules or tagging_rules(domain)
    conf = rules["confidence"]
    found: dict[tuple[str, str], dict] = {}

    def add(node_id, cid, method, variant):
        old = found.get((node_id, cid))
        if old is None or PRIORITY.index(method) < PRIORITY.index(old["method"]):
            found[(node_id, cid)] = {"node_id": node_id, "concept_id": cid, "method": method, "variant": variant,
                                     "confidence": conf[method]}

    concepts_ = spec["concepts"]
    by_id = {n["node_id"]: n for n in nodes}
    path = {n["node_id"]: _titles(n, by_id) for n in nodes}
    aggregation = {c["id"]: c["aggregation"] for c in concepts_}
    title_concepts: dict[str, set] = {}
    for n in nodes:
        seen: set = set()
        parent = by_id.get(n.get("parent_id"))
        if parent is not None and rules["_no_dict"].search(_titles(parent, by_id)):
            title_concepts[n["node_id"]] = seen   # inside accounting policies / audit: a title names a policy, not a figure
            continue
        for cid, s, _ in _hits((n["title"] or "").lower(), concepts_):
            if cid not in seen:
                seen.add(cid)
                add(n["node_id"], cid, "rule_title", s)
        title_concepts[n["node_id"]] = seen
    for t in tables:
        node_id = t.get("node_id")
        if not node_id or node_id not in path or rules["_other"].search(path[node_id]):
            continue
        no_stock = bool(rules["_movement"].search(by_id[node_id]["title"] or "")) or any(
            aggregation.get(c) == "flow" for c in title_concepts.get(node_id, ()))
        for raw in t.get("labels") or ():
            label = clean_label(raw)
            if not label or not any(informative(w, domain)
                                    for w in re.findall(r"[a-z]+|[\u4e00-\u9fff]+", label.lower())):
                continue
            for c in concepts_:
                if no_stock and c["aggregation"] == "stock":
                    continue
                hit = next((s for s in [*(c.get("variants") or ()), *(c.get("row_labels") or ())]
                            if norm(s) == norm(label)), None)
                if hit:
                    add(node_id, c["id"], "rule_row_label", hit)
    for node_id, text in own_text(nodes, pages).items():
        if rules["_other"].search(path[node_id]) or rules["_no_dict"].search(path[node_id]):
            continue
        low = text.lower()
        by: dict[str, list] = {}
        ctx, width = rules.get("_context"), int(rules.get("context_chars") or 0)
        for cid, s, span in _hits(low, concepts_):
            if ctx is not None and ctx.search(_sentence_window(low, span, width)):
                continue                      # a passing mention (minimum, sensitivity, fund, dividend base)
            by.setdefault(cid, []).append((s, span))
        near = rules["near_number"]
        for cid, hs in by.items():
            if len(hs) >= rules["dict_min"] and any(re.search(r"\d", low[max(0, a - near):b + near]) for _, (a, b) in hs):
                top = max({s for s, _ in hs}, key=lambda x: (sum(1 for s, _ in hs if s == x), x))
                add(node_id, cid, "rule_dict", top)
    ids = {n["node_id"] for n in nodes}
    for r in overrides.get("remove") or ():
        found.pop((r["node_id"], r["concept_id"]), None)
    for a in overrides.get("add") or ():
        if a["node_id"] in ids:
            add(a["node_id"], a["concept_id"], "manual", None)
    return sorted(found.values(), key=lambda r: (r["node_id"], r["concept_id"]))


def node_fields(rows: list[dict]) -> dict[str, dict]:
    by: dict[str, list[str]] = {}
    for r in rows:
        by.setdefault(r["node_id"], []).append(r["concept_id"])
    return {k: {"concept_tok": " ".join(sorted(v)), "concept_ids": sorted(v)} for k, v in by.items()}


def load_concepts(conn, spec: dict) -> dict[str, int]:
    """Upsert concepts and rewrite aliases and edges from concepts.yaml (one transaction; idempotent)."""
    from psycopg.types.json import Jsonb

    from kb_core.queries import pg_query

    q = lambda name: pg_query(name)[1]  # noqa: E731
    rows = alias_rows(spec)
    edges = spec.get("edges") or []
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(q("C01_upsert_concept"), [{
            "concept_id": c["id"], "name_en": c["name"]["en"], "name_zh": c["name"]["zh"], "value_type": c["value_type"],
            "aggregation": c["aggregation"], "default_period_kind": c["period_kind"], "definition": c.get("definition"),
            "derive": Jsonb({"expr": c["derive"]}) if c.get("derive") else None, "spec_version": spec["version"]}
            for c in spec["concepts"]])
        cur.execute(q("C02_clear_aliases_edges"))
        cur.executemany(q("C03_insert_alias"), rows)
        cur.executemany(q("C04_insert_edge"), [{"src": e["src"], "relation": e["relation"], "dst": e["dst"]} for e in edges])
        cur.execute(q("C05_delete_missing_concepts"), {"ids": [c["id"] for c in spec["concepts"]]})
    return {"concept": len(spec["concepts"]), "concept_alias": len(rows), "concept_edge": len(edges)}
