"""`kb-core eval recall`: retrieval recall on kb's question sets (port of kb scripts/eval.py recall mode).

Single-point questions run twice, with the asked years as `fiscal_years` and without; a question hits when one of the
top 5 evidence results (fact-layer results excluded) has a page range overlapping a gold physical page of the same
document. Cross-year questions run once with `group_by=fiscal_year, per_group=3, limit=10` and hit only when every
required year's top 3 hits that year's gold. Primary metrics count questions without `heldout_term`; held-out wordings
are reported separately. Search runs in-process through the traced service path (trace source `eval`).
"""

import hashlib
import json
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import yaml
from psycopg.types.json import Jsonb

from kb_core.config import Settings
from kb_core.paths import data_dir
from kb_core.queries import pg_query

TOP_K = 5
CROSS_YEAR = {"group_by": "fiscal_year", "per_group": 3, "limit": 10}

Call = Callable[[dict], dict]
GoldNodes = Callable[[dict], set[str]]


def page_hit(r: dict, gold: dict) -> bool:
    s, e = r["source"]["page_range"]
    return bool(set(range(s, e + 1)) & set(gold.get(r["source"]["doc_id"], [])))


def gold_years(gold: dict) -> list[int]:
    return sorted({int(re.search(r"_(\d{4})_", d)[1]) for d in gold})


def asked_years(q: dict) -> list[int]:
    """Years stated in the question (2000-2099); otherwise the year of the documents holding the gold pages."""
    return sorted({int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", q["query"])}) or gold_years(q["gold"])


def evidence(results: list[dict]) -> list[dict]:
    """Evidence results only (fact-layer results do not count toward the top k); ranks are positions among them."""
    out = [dict(r) for r in results if r["tier"] != "fact"]
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def _top(results: list[dict]) -> list[list]:
    return [[r["rank"], r["tier"], r["source"]["doc_id"], r["source"]["page_range"], r["title"][:50], r["node_id"]]
            for r in results[:TOP_K]]


def single(call: Call, q: dict, gold_nodes: GoldNodes) -> dict:
    gn = gold_nodes(q["gold"])
    row = {"id": q["id"], "lang": q["lang"], "category": q.get("category"), "variant_of": q.get("variant_of"),
           "heldout_term": q.get("heldout_term"), "query": q["query"], "fiscal_years": asked_years(q)}
    for key, extra in (("with_year", {"fiscal_years": row["fiscal_years"]}), ("no_year", {})):
        body = call({"query": q["query"], "limit": TOP_K, **extra})
        top = evidence(body["results"])[:TOP_K]
        row[key] = {"node_hit_rank": next((r["rank"] for r in top if r["node_id"] in gn), None),
                    "page_hit_rank": next((r["rank"] for r in top if page_hit(r, q["gold"])), None),
                    "hit_node_ids": [r["node_id"] for r in top if page_hit(r, q["gold"])],
                    "top5": _top(top), "trace_id": body["trace_id"], "query_terms": body["scope"]["query_terms"]}
    return row


def cross_year(call: Call, q: dict, gold_nodes: GoldNodes) -> dict:
    body = call({"query": q["query"], **CROSS_YEAR})
    ev = evidence(body["results"])
    per_year = {}
    for y in q["years"]:
        gold = q["gold"][y]
        group = [r for r in ev if r["group"] == str(y)][:CROSS_YEAR["per_group"]]
        gn = gold_nodes(gold)
        per_year[y] = {"node": any(r["node_id"] in gn for r in group), "page": any(page_hit(r, gold) for r in group),
                       "page_hit_pos": next((i + 1 for i, r in enumerate(group) if page_hit(r, gold)), None),
                       "hit_node_ids": [r["node_id"] for r in group if page_hit(r, gold)],
                       "group_top3": _top(group)[:3]}
    return {"id": q["id"], "lang": q["lang"], "category": "cross_year", "variant_of": q.get("variant_of"),
            "heldout_term": q.get("heldout_term"), "query": q["query"], "years": q["years"], "per_year": per_year,
            "node_hit": all(v["node"] for v in per_year.values()),
            "page_hit": all(v["page"] for v in per_year.values()),
            "trace_id": body["trace_id"], "query_terms": body["scope"]["query_terms"]}


def summarize(out: dict, legacy_ids: set[str]) -> dict:
    """Primary metrics and the cross-year count use only questions without `heldout_term`. Held-out: legacy = the
    P1 questions listed in eval/heldout_terms.yaml, new = questions with a `heldout_term` (single-point questions hit
    on the with-year variant, cross-year questions on every year)."""
    s = [r for r in out["single"] if not r.get("heldout_term")]
    c = [r for r in out["cross_year"] if not r.get("heldout_term")]

    def hits(rows, key, metric):
        return sum(r[key][metric] is not None for r in rows)

    def hit(r):
        return r["page_hit"] if "page_hit" in r else r["with_year"]["page_hit_rank"] is not None
    rows = out["single"] + out["cross_year"]
    legacy = [r for r in rows if r["id"] in legacy_ids and not r.get("heldout_term")]
    new = [r for r in rows if r.get("heldout_term")]
    return {
        "single": {"questions": len(s),
                   "with_year": {"node_hit_at5": hits(s, "with_year", "node_hit_rank"),
                                 "page_hit_at5": hits(s, "with_year", "page_hit_rank")},
                   "no_year": {"node_hit_at5": hits(s, "no_year", "node_hit_rank"),
                               "page_hit_at5": hits(s, "no_year", "page_hit_rank")}},
        "cross_year": {"questions": len(c), "node_hit": sum(r["node_hit"] for r in c),
                       "page_hit": sum(r["page_hit"] for r in c)},
        "x01_page_hit": next((r["page_hit"] for r in c if r["id"] == "x01"), None),
        "heldout": {"legacy": {"questions": len(legacy), "hits": sum(map(hit, legacy))},
                    "new": {"questions": len(new), "hits": sum(map(hit, new))}},
    }


def result_rows(out: dict) -> list[dict]:
    """eval.eval_result rows: page-range hit and rank; node-level hits and the top results go in detail."""
    rows = []
    for r in out["single"]:
        meta = {"query": r.get("query"), "lang": r["lang"], "category": r.get("category"),
                "heldout_term": r.get("heldout_term")}
        for v in ("with_year", "no_year"):
            x = r[v]
            rows.append({"question_id": r["id"], "variant": v,
                         "year": r["fiscal_years"][0] if v == "with_year" and r.get("fiscal_years") else None,
                         "hit": x["page_hit_rank"] is not None, "best_rank": x["page_hit_rank"],
                         "hit_node_ids": x.get("hit_node_ids"), "trace_id": x["trace_id"],
                         "detail": {**meta, "node_hit_rank": x["node_hit_rank"], "top5": x["top5"],
                                    "query_terms": x["query_terms"],
                                    "fiscal_years": r.get("fiscal_years") if v == "with_year" else None}})
    for r in out["cross_year"]:
        meta = {"query": r.get("query"), "lang": r["lang"], "category": "cross_year",
                "heldout_term": r.get("heldout_term")}
        for y, x in r["per_year"].items():
            rows.append({"question_id": r["id"], "variant": "crossyear", "year": int(y), "hit": x["page"],
                         "best_rank": x.get("page_hit_pos"), "hit_node_ids": x.get("hit_node_ids"),
                         "trace_id": r["trace_id"],
                         "detail": {**meta, "node_hit": x["node"], "group_top3": x["group_top3"],
                                    "query_terms": r["query_terms"]}})
    return rows


def _git_sha() -> str | None:
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).parent)
    return r.stdout.strip() if r.returncode == 0 else None


def question_file(name: str) -> Path:
    p = Path(name)
    return p if p.suffix else data_dir("eval") / f"{name}.yaml"


def run(settings: Settings, sets: list[str], out_dir: Path, label: str | None = None,
        subject: str | None = "full_access") -> dict:
    """Run the recall eval over the named question sets; write eval.eval_run/eval_result and a JSON result file."""
    from kb_core.retrieval import aliases, context
    from kb_core.retrieval.search import ranking, search

    started = datetime.now(UTC)
    run_id = f"eval-recall-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    ctx = context.init(settings)
    try:
        def call(body: dict) -> dict:
            # the regression gate runs as the full-access subject (round 2 W3); other subjects are reported apart
            return search(body, source="eval", session_id=run_id, subject=subject)

        def gold_nodes(gold: dict) -> set[str]:
            return {n for doc_id, pages in gold.items() if doc_id in ctx.catalog.trees
                    for p in pages for n in ctx.catalog.primary(doc_id).deepest_covering(p)}

        files = [question_file(s) for s in sets]
        out = {"run_id": run_id, "kind": "recall", "single": [], "cross_year": []}
        for f in files:
            for q in yaml.safe_load(f.read_text())["questions"]:
                if "years" in q:
                    out["cross_year"].append(cross_year(call, q, gold_nodes))
                else:
                    out["single"].append(single(call, q, gold_nodes))
        terms_file = data_dir("eval") / "heldout_terms.yaml"
        terms = yaml.safe_load(terms_file.read_text())["terms"] if terms_file.exists() else []
        out["summary"] = summarize(out, {t["question_id"] for t in terms})
        config = {"mode": "inprocess", "subject": subject, "top_k": TOP_K, "crossyear": CROSS_YEAR, "ranking": ranking(),
                  "aliases": aliases.enabled()}
        out["config"] = config
        question_set = [{"file": f.name, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()} for f in files]
        rows = result_rows(out)
        with ctx.lock, ctx.pg.transaction():
            ctx.pg.execute(pg_query("V3_insert_eval_run")[1], {
                "run_id": run_id, "kind": "recall", "started_at": started, "finished_at": datetime.now(UTC),
                "git_sha": _git_sha(), "config": Jsonb(config), "question_set": Jsonb(question_set),
                "note": None, "label": label})
            with ctx.pg.cursor() as cur:
                cur.executemany(pg_query("V4_insert_eval_result")[1],
                                [{**r, "detail": Jsonb(r["detail"]), "run_id": run_id} for r in rows])
    finally:
        context.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"recall_{run_id.removeprefix('eval-recall-')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return {"run_id": run_id, "file": str(path), "summary": out["summary"]}
