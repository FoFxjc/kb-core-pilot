"""Admin endpoints (api-contract §8): documents, import, runs, traces, sessions, evaluations, the full primary tree and
page regions. HTTP only, used by the UI and evaluation; not MCP tools. Reads go through queries/pg templates."""

import uuid
from datetime import datetime
from pathlib import Path

import yaml

from kb_core.intake.importer import import_path
from kb_core.intake.package import PackageError
from kb_core.paths import data_dir
from kb_core.pg.db import connect
from kb_core.retrieval import context
from kb_core.retrieval.core import ApiError

SOURCES = ["mcp", "chat", "eval", "ui", "http"]
TOOLS = ["search", "browse", "read", "resolve_concept", "get_metric_series"]


def _limit(value, default: int, top: int) -> int:
    if value is None:
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ApiError("INVALID_PARAM", f"limit must be an integer 1-{top}", param="limit") from None
    if not 1 <= n <= top:
        raise ApiError("INVALID_PARAM", f"limit must be 1-{top}", param="limit")
    return n


def _choice(value, name: str, allowed: list[str]) -> str | None:
    if value is not None and value not in allowed:
        raise ApiError("INVALID_PARAM", f"{name} must be one of {allowed}", param=name, allowed=allowed)
    return value


def _time(value, name: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ApiError("INVALID_PARAM", f"{name} must be an ISO 8601 time", param=name) from None


def trace_uuid(trace_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(hex=trace_id.removeprefix("tr_"))
    except ValueError:
        raise ApiError("NOT_FOUND", f"no trace {trace_id!r}") from None


def _trace_row(r: dict) -> dict:
    out = {k: v for k, v in r.items() if k not in ("id", "kind")}
    out["trace_id"] = f"tr_{r['trace_id'].hex}"
    out["tool"] = r["kind"].removeprefix("tool.")
    return out


def docs(subject: str | None = None) -> dict:
    """Documents the subject may see (the document view's picker)."""
    from kb_core.access import scope

    with scope.acting_as(subject):
        visible = context.current().catalog.visible_docs()
    return {"docs": [d for d in context.current().pg_rows("A1_admin_docs") if d["doc_id"] in visible]}


def visible_page(doc_id: str, page_no: int, subject: str | None) -> dict:
    """The page's metadata if the subject may see it; a hidden page is NOT_FOUND exactly like a missing one."""
    from kb_core.access import scope

    cat = context.current().catalog
    with scope.acting_as(subject):
        meta = (context.current().pg_rows("A8_page_meta", {"doc_id": doc_id, "page_no": page_no}) or [None])[0] \
            if doc_id in cat.visible_docs() else None
        if meta is None or not scope.visible(meta.get("access")):
            raise ApiError("NOT_FOUND", f"no page {page_no} in {doc_id!r}")
    return meta


def runs(doc_id: str | None, stage: str | None, limit) -> dict:
    return {"runs": context.current().pg_rows("A2_admin_runs", {"doc_id": doc_id, "stage": stage},
                                              limit=_limit(limit, 50, 500))}


def traces(q) -> dict:
    cursor = q.get("cursor")
    if cursor is not None and not (str(cursor).isascii() and str(cursor).isdigit() and int(cursor) < 2 ** 63):
        raise ApiError("INVALID_PARAM", "cursor must be the next_cursor of a previous page", param="cursor")
    limit = _limit(q.get("limit"), 50, 200)
    rows = context.current().pg_rows("A3_admin_traces", {
        "source": _choice(q.get("source"), "source", SOURCES), "tool": _choice(q.get("tool"), "tool", TOOLS),
        "session_id": q.get("session_id"), "from": _time(q.get("from"), "from"), "to": _time(q.get("to"), "to"),
        "cursor": int(cursor) if cursor is not None else None}, limit=limit)
    return {"traces": [_trace_row(r) for r in rows],
            "next_cursor": str(rows[-1]["id"]) if len(rows) == limit else None}


def trace(trace_id: str) -> dict:
    rows = context.current().pg_rows("A4_admin_trace", {"trace_id": trace_uuid(trace_id)})
    if not rows:
        raise ApiError("NOT_FOUND", f"no trace {trace_id!r}")
    out = _trace_row(rows[0])
    out["events"] = [_trace_row(r) for r in rows[1:]]
    return out


def session(session_id: str) -> dict:
    rows = context.current().pg_rows("A5_admin_session", {"session_id": session_id})
    if not rows:
        raise ApiError("NOT_FOUND", f"no session {session_id!r}")
    return {"session_id": session_id, "calls": [_trace_row(r) for r in rows]}


def evals(kind: str | None, limit) -> dict:
    return {"runs": context.current().pg_rows("A6_admin_evals",
                                              {"kind": _choice(kind, "kind", ["recall", "agent", "tree", "concepts"])},
                                              limit=_limit(limit, 20, 200))}


def doc_nodes(doc_id: str, subject: str | None = None) -> dict:
    """The document's full tree for the document view, as the subject may see it (hidden nodes left out; a hidden
    document is unknown, like a missing one)."""
    from kb_core.access import scope

    cat = context.current().catalog
    with scope.acting_as(subject):
        visible_docs = cat.visible_docs()
        if doc_id not in visible_docs:
            raise ApiError("UNKNOWN_DOC", f"unknown doc_id: {doc_id}", candidates=sorted(visible_docs))
        tree = cat.primary(doc_id)
        shown = {nid for nid, n in tree.nodes.items() if scope.visible(n.get("access"))}
    nodes = [{"node_id": nid, "parent_id": n["parent_id"], "depth": n["depth"], "title": n["title"],
              "start_page": n["start_page"], "end_page": n["end_page"], "page_label_range": n["page_label_range"],
              "section_type": n["section_type"], "concepts": cat.node_concepts.get(nid, [])}
             for nid, n in sorted(tree.nodes.items(), key=lambda kv: (kv[1]["ord"], kv[0])) if nid in shown]
    return {"doc_id": doc_id, "tree_source": tree.tree_source, "nodes": nodes}


def page_regions(doc_id: str, page_no: int, subject: str | None = None) -> dict:
    meta = visible_page(doc_id, page_no, subject)
    ctx = context.current()
    return {"doc_id": doc_id, "page_no": page_no, "page_label": meta.get("page_label"),
            "width": meta.get("width"), "height": meta.get("height"),
            "regions": ctx.pg_rows("A7_page_regions", {"doc_id": doc_id, "page_no": page_no})}


def import_packages(path: str | None) -> dict:
    """Import a package or delivery folder on the server, as `kb-core import` (one executor writes: the caller)."""
    ctx = context.current()
    if not path:
        raise ApiError("INVALID_PARAM", "path is required", param="path")
    try:
        with connect(ctx.settings) as conn:
            done = import_path(conn, ctx.settings, Path(path))
    except PackageError as e:
        raise ApiError("INVALID_PARAM", str(e), param="path") from None
    return {"imported": [{"doc_id": r.doc_id, "package": r.package, "created": r.created} for r in done]}


def config(live_chat: bool = False, role_picker: bool = False) -> dict:
    """What the UI may offer: recorded sessions always; live chat when it is configured (GET /v1/admin/chat/status
    says why not); the dev role picker only without identity (auth mode none; hidden behind the SSO gateway)."""
    return {"contract": "v1", "llm_enabled": context.current().settings.llm_enabled, "live_chat": live_chat,
            "mode": "live" if live_chat else "replay", "role_picker": role_picker}


def replay_dir() -> Path:
    return data_dir("eval") / "results"


def replays() -> dict:
    """Recorded MCP sessions (eval/results/mcp_demo_*.yaml): questions, the agent's answer and its tool calls."""
    out = []
    for f in sorted(replay_dir().glob("mcp_demo_*.yaml")):
        d = yaml.safe_load(f.read_text()) or {}
        out.append({"id": f.stem, "run": d.get("run"), "session_id": d.get("session_id"),
                    "questions": d.get("questions") or {}, "answer": d.get("answer"),
                    "tool_calls": d.get("tool_calls") or []})
    return {"replays": out}
