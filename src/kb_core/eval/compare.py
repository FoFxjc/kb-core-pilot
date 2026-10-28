"""Compare an evaluation result with a baseline (round 2: every PR is checked against eval/results/baseline_round2/).

Inputs are recall result files (`summary`, `single`, `cross_year`) or `kb-core eval snapshot` files (`facts`, `tree`);
each block present in the baseline is compared.

Regressions:
- recall: a summary count that goes down (including the number of questions), a question missing from the new run,
  or a question that loses a hit it had (rank becomes null, or a cross-year hit becomes false), even when another
  question's gain keeps the totals level;
- facts: fewer observations, facts or agreed facts, more conflicts, or a metric no longer covered;
- tree: a lower spot-check accuracy on any document, or a document with no accuracy.

Review items (listed, not failing; the PR must explain each): more single-source facts, a change in restated facts, and
a tree accuracy measured on a different sample (seed, sheet or size) than the baseline. The tree block compares
recorded judgements (`kb-core eval tree --record`), not the current tree: a tree change is only measured when its
sheets are judged and recorded again.

Explained exceptions: a lost node hit is waived only by an entry naming the question, variant and field with a
`reason`, `approved_by` and the `pr` it was approved for; it applies only to a run for that PR. A lost page hit needs
the same plus `page_hit: true` (the project owner approved page-hit exceptions explicitly for W1, 2026-10-27). The summary
count it lowers is waived with it. Entries without approval (or malformed) waive nothing and are listed under
`pending_exceptions`; approved entries for this PR that match nothing are listed under `unused_exceptions`.

Per question it also lists every hit-rank change and top-k list that differs. Top-k entries are compared by
(tier, doc, pages, title), not node id: a tree change renumbers node ids.
"""

from collections.abc import Iterator

WAIVABLE = {"node_hit_rank", "node_hit"}
FACT_UP = ("observations", "facts", "agreed")  # these going down is a regression
FACT_DOWN = ("conflict",)  # this going up is a regression
SAMPLE = ("seed", "sheet", "sampled")


def _counts(summary: dict, prefix: str = "") -> Iterator[tuple[str, int]]:
    for k, v in summary.items():
        name = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from _counts(v, name + ".")
        elif isinstance(v, int) and not isinstance(v, bool):
            yield name, v


def _key(top: list) -> list[tuple]:
    return [(r[1], r[2], tuple(r[3]) if r[3] else None, r[4]) for r in top or []]


def _summary_metric(row: dict, variant: str, field: str = "node_hit_rank") -> str:
    """The summary count a lost hit lowers."""
    page = field in ("page_hit_rank", "page_hit")
    if variant == "cross_year":
        return "cross_year.page_hit" if page else "cross_year.node_hit"
    if row.get("heldout_term"):
        return "heldout.new.hits"
    return f"single.{variant}.{'page' if page else 'node'}_hit_at5"


def _recall(base: dict, new: dict, regressions: list, improvements: list, lost: list) -> dict:
    b, n = dict(_counts(base["summary"])), dict(_counts(new.get("summary") or {}))
    regressions += [{"metric": m, "base": b[m], "new": n.get(m, 0)} for m in b if n.get(m, 0) < b[m]]
    improvements += [{"metric": m, "base": b.get(m, 0), "new": n[m]} for m in n
                     if n[m] > b.get(m, 0) and not m.endswith("questions")]
    if base["summary"].get("x01_page_hit") and not (new.get("summary") or {}).get("x01_page_hit"):
        regressions.append({"metric": "x01_page_hit", "base": True, "new": False})

    rank_changes, topk_changed = [], []
    new_single = {r["id"]: r for r in new.get("single", [])}
    for r in base.get("single", []):
        other = new_single.get(r["id"])
        if other is None:
            regressions.append({"metric": "missing_question", "id": r["id"]})
            continue
        for variant in ("with_year", "no_year"):
            x, y = r.get(variant) or {}, other.get(variant) or {}
            for field in ("node_hit_rank", "page_hit_rank"):
                if x.get(field) is not None and y.get(field) is None:
                    lost.append(({"metric": "lost_hit", "id": r["id"], "variant": variant, "field": field},
                                 _summary_metric(r, variant, field)))
                if x.get(field) != y.get(field):
                    rank_changes.append({"id": r["id"], "variant": variant, "field": field,
                                         "base": x.get(field), "new": y.get(field)})
            if _key(x.get("top5")) != _key(y.get("top5")):
                topk_changed.append(f"{r['id']}/{variant}")
    new_cross = {r["id"]: r for r in new.get("cross_year", [])}
    for r in base.get("cross_year", []):
        other = new_cross.get(r["id"])
        if other is None:
            regressions.append({"metric": "missing_question", "id": r["id"]})
            continue
        for field in ("node_hit", "page_hit"):
            if r.get(field) and not other.get(field):
                lost.append(({"metric": "lost_hit", "id": r["id"], "variant": "cross_year", "field": field},
                             _summary_metric(r, "cross_year", field)))
            if r.get(field) != other.get(field):
                rank_changes.append({"id": r["id"], "variant": "cross_year", "field": field,
                                     "base": r.get(field), "new": other.get(field)})
        for year, g in (r.get("per_year") or {}).items():
            if _key(g.get("group_top3")) != _key(((other.get("per_year") or {}).get(year) or {}).get("group_top3")):
                topk_changed.append(f"{r['id']}/{year}")
    compared = sum(2 for r in base.get("single", []) if r["id"] in new_single) + sum(
        len(r.get("per_year") or {}) for r in base.get("cross_year", []) if r["id"] in new_cross)
    return {"rank_changes": rank_changes, "topk_changed": topk_changed, "topk_compared": compared}


def _facts(base: dict, new: dict, regressions: list, improvements: list, review: list) -> None:
    for k in FACT_UP + FACT_DOWN:
        bv, nv = base.get(k, 0), (new or {}).get(k, 0)
        if (k in FACT_UP and nv < bv) or (k in FACT_DOWN and nv > bv):
            regressions.append({"metric": f"facts.{k}", "base": bv, "new": nv})
        elif nv != bv and k in FACT_UP:
            improvements.append({"metric": f"facts.{k}", "base": bv, "new": nv})
    for k, up_only in (("single", True), ("restated", False)):
        bv, nv = base.get(k, 0), (new or {}).get(k, 0)
        if nv > bv or (nv != bv and not up_only):
            review.append({"metric": f"facts.{k}", "base": bv, "new": nv})
    missing = sorted(set(base.get("metrics_covered") or []) - set((new or {}).get("metrics_covered") or []))
    if missing:
        regressions.append({"metric": "facts.metrics_covered", "missing": missing})


def _tree(base: dict, new: dict, regressions: list, improvements: list, review: list) -> None:
    for doc, acc in base.items():
        other = (new or {}).get(doc) or {}
        bv, nv = acc.get("value"), other.get("value")
        if bv is None:
            continue
        if nv is None or nv < bv:
            regressions.append({"metric": f"tree.{doc}", "base": bv, "new": nv})
        elif nv > bv:
            improvements.append({"metric": f"tree.{doc}", "base": bv, "new": nv})
        if other and [acc.get(k) for k in SAMPLE] != [other.get(k) for k in SAMPLE]:
            review.append({"metric": f"tree.{doc}", "reason": "different sample",
                           "base": [acc.get(k) for k in SAMPLE], "new": [other.get(k) for k in SAMPLE]})


PAGE_FIELDS = {"page_hit_rank", "page_hit"}


def _approved(e: dict) -> bool:
    """Complete and approved; a page-hit loss needs `page_hit: true` on top (the project owner approves those one by one)."""
    return (all(e.get(k) for k in ("id", "variant", "field", "reason", "approved_by", "pr"))
            and (e.get("field") in WAIVABLE or (e.get("field") in PAGE_FIELDS and e.get("page_hit") is True)))


def compare(base: dict, new: dict, exceptions: list[dict] | None = None, pr: int | None = None) -> dict:
    if not {"summary", "facts", "tree"} & set(base):
        raise ValueError("baseline has none of the blocks summary, facts, tree (not a recall or snapshot file)")
    regressions: list[dict] = []
    improvements: list[dict] = []
    review: list[dict] = []
    lost: list[tuple[dict, str]] = []  # (lost-hit regression, summary count it lowers)
    out: dict = {"rank_changes": [], "topk_changed": [], "topk_compared": 0}
    if "summary" in base:
        out.update(_recall(base, new, regressions, improvements, lost))
    if "facts" in base:
        _facts(base["facts"], new.get("facts"), regressions, improvements, review)
    if "tree" in base:
        _tree(base["tree"], new.get("tree"), regressions, improvements, review)

    exceptions = exceptions or []
    valid = [e for e in exceptions if _approved(e)]
    mine = [e for e in valid if pr is not None and str(e["pr"]) == str(pr)]
    approved = {(e["id"], e["variant"], e["field"]): e for e in mine}
    used: set[tuple] = set()
    waived, waived_by_metric = [], {}
    for reg, metric in lost:
        key = (reg["id"], reg["variant"], reg["field"])
        e = approved.get(key)
        if e:
            used.add(key)
            waived.append({**reg, "reason": e["reason"], "approved_by": e["approved_by"]})
            waived_by_metric[metric] = waived_by_metric.get(metric, 0) + 1
        else:
            regressions.append(reg)
    waived_counts = []
    for reg in list(regressions):
        m = reg.get("metric")
        if m in waived_by_metric and "base" in reg and reg["new"] + waived_by_metric[m] >= reg["base"]:
            regressions.remove(reg)
            waived_counts.append(reg)
    return {"regressions": regressions, "improvements": improvements, "review": review, "waived": waived,
            "waived_counts": waived_counts, "pending_exceptions": [e for e in exceptions if not _approved(e)],
            "other_pr_exceptions": [e for e in valid if e not in mine],
            "unused_exceptions": [e for e in mine if (e["id"], e["variant"], e["field"]) not in used], **out}
