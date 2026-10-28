"""`kb-core eval headings`: compare a blind judge's heading list on sampled pages with the primary tree (round 2
T1.2). The judge lists every heading that starts a section on each sampled physical page, from the PDF only; this
module never reads another system's tree.

Per document: `found` = judged headings with a primary node starting on the same page with the same normalised title
(a line wrap may make one title a prefix of the other); `missed` = the rest, of which `misplaced` have a matching
node starting on a different page; `extra` = primary nodes starting on a sampled page that match no judged heading
(contents-group nodes, printed only on the contents page by kb's rule, are never extra).
"""

import re
import unicodedata

CONTINUED = re.compile(r"\(\s*(continued|cont'?d|\u7eed)\s*\)", re.I)  # after NFKC: full-width brackets are ASCII
BULLET = re.compile(r"^[\u2022\u00b7*\-]+\s*")
SPACE_BETWEEN_CJK = re.compile(r"(?<=[\u3000-\u9fff\uff00-\uffef])\s+|\s+(?=[\u3000-\u9fff\uff00-\uffef])")
MIN_PREFIX = 6


def norm_title(title: str) -> str:
    t = unicodedata.normalize("NFKC", title or "")
    t = CONTINUED.sub(" ", t)
    t = BULLET.sub("", t.strip())
    t = re.sub(r"\s+", " ", t).strip().lower()
    t = SPACE_BETWEEN_CJK.sub("", t)
    return t.rstrip(" .:;,")


def _same(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= MIN_PREFIX and long_.startswith(short)


def match_headings(sheet: dict, nodes: list[dict]) -> dict:
    """`nodes`: the document's primary-tree nodes (title, start_page, origin)."""
    pages = {}
    for p in sheet["pages"]:
        if p.get("headings") is None:
            raise ValueError(f"{sheet['doc_id']} page {p['page']} is not judged (headings must be a list)")
        pages[p["page"]] = [h["title"] for h in p["headings"]]
    normed = [(norm_title(n["title"]), n) for n in nodes]
    found, missed, misplaced, matched_nodes = 0, [], [], set()
    for page, titles in sorted(pages.items()):
        for title in titles:
            t = norm_title(title)
            hit = next((i for i, (nt, n) in enumerate(normed)
                        if n["start_page"] == page and i not in matched_nodes and _same(t, nt)), None)
            if hit is not None:
                found += 1
                matched_nodes.add(hit)
                continue
            missed.append({"page": page, "title": title})
            elsewhere = [n["start_page"] for nt, n in normed if _same(t, nt)]
            if elsewhere:
                misplaced.append({"page": page, "title": title, "node_pages": sorted(set(elsewhere))})
    extra = [{"page": n["start_page"], "title": n["title"]} for i, (nt, n) in enumerate(normed)
             if n["start_page"] in pages and i not in matched_nodes and n.get("origin") != "toc_group"]
    judged = sum(len(t) for t in pages.values())
    return {"doc_id": sheet["doc_id"], "seed": sheet.get("seed"), "pages": len(pages), "judged": judged,
            "found": found, "missed": missed, "misplaced": misplaced, "extra": extra,
            "missed_rate": round(len(missed) / judged, 4) if judged else 0.0}
