"""Tool call tracing (port of kb service/tracing.py; api-contract §10): one quality.trace_event per call
(kind tool.<name>) holding the request, the response and the trace detail (per-route ranks, coverage drops, layer
decisions, final ES DSL / SQL per template); the response's gaps also go to quality.gap_log."""

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from kb_core.retrieval import context
from kb_core.retrieval.core import ApiError, envelope, new_trace_id, with_severity


def record(tool: str, trace_id: uuid.UUID, params: dict, output: dict, started: datetime, ms: int, status: str,
           error: str | None, source: str, session_id: str | None, doc_id: str | None = None) -> None:
    ctx = context.current()
    ctx.pg_execute("G5_trace_insert", {"trace_id": trace_id, "span_id": uuid.uuid4(), "kind": f"tool.{tool}",
                                       "source": source, "doc_id": doc_id, "session_id": session_id, "input": params,
                                       "output": output, "started_at": started, "duration_ms": ms, "status": status,
                                       "error": error})
    for g in output.get("gaps") or []:
        ctx.pg_execute("G6_gap_insert", {"doc_id": g.get("doc_id"), "trace_id": trace_id, "code": g["code"],
                                         "detail": g})


def compact(results: list[dict]) -> list[dict]:
    """What a trace keeps of each result (as kb did): identity, layer and location, never page text or images."""
    out = []
    for r in results:
        if "page_no" in r:
            out.append({"rank": r.get("rank"), "tier": r.get("tier"), "page_no": r["page_no"],
                        "chars": len(r.get("text") or ""), "tables": len(r.get("tables") or []),
                        "image": bool(r.get("image"))})
        else:
            src = r.get("source") or {}
            out.append({k: v for k, v in {"rank": r.get("rank"), "tier": r.get("tier"), "node_id": r.get("node_id"),
                                          "doc_id": src.get("doc_id"), "page_range": src.get("page_range"),
                                          "score": r.get("score"), "concept_id": r.get("concept_id"),
                                          "fiscal_year": r.get("fiscal_year")}.items() if v is not None})
    return out


def traced(tool: str, params: dict, fn: Callable, source: str = "http", session_id: str | None = None,
           subject: str | None = None) -> dict:
    """Run a tool function returning (results, scope, gaps, truncated, detail[, next_]) as `subject` (a role; None =
    public) and record the call."""
    from kb_core.access import scope as access_scope
    from kb_core.access.policy import load_roles

    trace_id, started, t0 = new_trace_id(), datetime.now(UTC), time.perf_counter()
    if subject and subject not in load_roles():
        raise ApiError("INVALID_PARAM", f"unknown subject {subject!r}", param="subject", allowed=sorted(load_roles()))
    try:
        with access_scope.acting_as(subject):
            out = fn(params)
            n_filtered = access_scope.filtered()
    except ApiError as e:
        record(tool, trace_id, params, {"error": e.body()["error"]}, started,
               int((time.perf_counter() - t0) * 1000), "error", e.message, source, session_id)
        raise
    results, scope, gaps, truncated, detail, *rest = out
    gaps = with_severity(gaps)                 # every tool's gaps carry a severity (api-contract §4.4)
    next_ = rest[0] if rest else None
    env = envelope(tool, results, scope, gaps, trace_id, truncated, next_)
    record(tool, trace_id, params, {"results": compact(results), "scope": scope, "gaps": gaps, "truncated": truncated,
                                    "next": next_, "detail": {**(detail or {}), "subject": subject or "public"}},
           started, int((time.perf_counter() - t0) * 1000), "ok", None, source, session_id)
    audit(tool, trace_id, subject or "public", results, n_filtered, source)
    return env


def audit(tool: str, trace_id: uuid.UUID, subject: str, results: list[dict], n_filtered: int, source: str) -> None:
    """quality.access_audit (round 2 W3, T3.7): subject, tool, returned ids, how much the policy hid."""
    from psycopg.types.json import Jsonb

    ids = []
    for r in results:
        if r.get("node_id"):
            ids.append(r["node_id"])
        elif r.get("page_no") is not None:
            ids.append(f"page:{r['page_no']}")
        elif r.get("concept_id"):
            ids.append(f"fact:{r['concept_id']}:{r.get('fiscal_year')}")
    from kb_core.access import scope as access_scope

    context.current().pg_execute("G8_access_audit_insert", {"trace_id": trace_id, "user_id": access_scope.user(),
                                                            "subject": subject, "tool": tool,
                                                            "returned_ids": ids, "n_filtered": n_filtered,
                                                            "detail": Jsonb({"source": source})})
