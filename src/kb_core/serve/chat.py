"""Live chat (round 2, W4; ported from kb service/chat.py, D25): a server-side agent loop over the five retrieval
tools, through a chat-completions-compatible endpoint configured with KB_CORE_LLM_* and KB_CORE_CHAT_*.

- Tools are called in-process (the same functions as HTTP and MCP); names, descriptions and parameter schemas come
  from the MCP server, and each tool result is the text MCP returns to an agent (without image data).
- At most `chat_max_tool_calls` tool calls per session, counted across turns; the remaining count ends every tool
  result, so the cost is visible to the model. One live turn runs at a time: `prepare` claims the slot (a second
  request is refused at once) and the turn releases it; a claim whose stream never started expires after
  STALE_CLAIM_S.
- History: every assistant message is appended exactly as the model returned it (including any reasoning), and is
  saved with the turn's `agent.answer` trace event, so a session survives a restart. A turn without a final answer
  (error, limit, truncation, disconnect) is rolled back, so the next turn never carries an unanswered tool call.
- Tracing: tool calls have source `chat` and the server-generated session id; each turn writes one `agent.answer`.
- Each finished answer goes through the number check (serve/numbers.py); unverified numbers are reported, not
  removed.
- Every model call, failed ones included, appends one line (no key, no content) to <store>/chat/model_calls.jsonl;
  KB_CORE_CHAT_BUDGET_CALLS caps the total.
"""

import contextlib
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import anyio
import httpx
from starlette.concurrency import run_in_threadpool

from kb_core.config import Settings
from kb_core.retrieval import context
from kb_core.retrieval.browse import browse, render_text
from kb_core.retrieval.concepts import resolve_concept
from kb_core.retrieval.core import ApiError
from kb_core.retrieval.facts import get_metric_series
from kb_core.retrieval.read import read
from kb_core.retrieval.search import search
from kb_core.serve.mcp import texts
from kb_core.serve.numbers import check_numbers, evidence_from_tool_results

log = logging.getLogger("kb_core.chat")

TOOLS: dict[str, Callable] = {"search": search, "browse": browse, "read": read, "resolve_concept": resolve_concept,
                              "get_metric_series": get_metric_series}
SYSTEM_EXTRA = ("\nYou answer questions on the chat page of the knowledge base console. Verify only with these tools; "
                "for every number give the document (doc_id), physical page and printed page. Numbers in your answer "
                "are checked against the tool results you received.\n"
                "LANGUAGE: always write the whole answer in English, whatever the language of the question, the rules "
                "above or the sources. Quote Chinese source text only when needed, followed by an English translation.")
STALE_CLAIM_S = 60
_THINK = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL)

ModelCall = Callable[[dict], Awaitable[dict]]
RunTool = Callable[[str, dict, str], tuple[int, dict]]
Record = Callable[[str, datetime, int, str, dict, str, str | None], str]


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def run_tool(name: str, args: dict, session_id: str, subject: str | None = None,
             user: str | None = None) -> tuple[int, dict]:
    """Call one retrieval tool in-process with source "chat" as the session's role and user; (HTTP status, body)."""
    fn = TOOLS.get(name)
    if fn is None:
        err = ApiError("INVALID_PARAM", f"unknown tool {name!r}", param="name", allowed=sorted(TOOLS))
        return err.http_status, err.body()
    args = {k: v for k, v in args.items() if v is not None}       # as MCP does: omitted, not null
    from kb_core.access import scope as access_scope

    try:
        with access_scope.as_user(user):
            return 200, fn(args, source="chat", session_id=session_id, subject=subject)
    except ApiError as e:
        return e.http_status, e.body()


def tool_text(name: str, status: int, body: dict) -> str:
    """The text MCP gives an agent for this result: compact JSON without image data (plus browse's outline)."""
    if status == 200:
        body = dict(body, results=[dict(r, image={k: v for k, v in r["image"].items() if k != "data_base64"})
                                   if isinstance(r, dict) and r.get("image") else r for r in body.get("results", [])])
    text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if status == 200 and name == "browse":
        text += "\n" + render_text(body["results"])
    return text


def record_answer(session_id: str, started: datetime, ms: int, message: str, out: dict, status: str,
                  error: str | None) -> str:
    """Write the turn's agent.answer trace event; returns its trace id (tr_<hex>)."""
    trace_id = uuid.uuid4()
    context.current().pg_execute("G5_trace_insert", {
        "trace_id": trace_id, "span_id": uuid.uuid4(), "kind": "agent.answer", "source": "chat", "doc_id": None,
        "session_id": session_id, "input": {"message": message, "model": out.get("model")}, "output": out,
        "started_at": started, "duration_ms": ms, "status": status, "error": error})
    return f"tr_{trace_id.hex}"


def load_session(session_id: str) -> dict | None:
    rows = context.current().pg_rows("G7_chat_last_answer", {"session_id": session_id})
    return rows[0]["output"] if rows else None


def thinking_of(message: dict) -> str:
    """Reasoning the model exposed: a reasoning field, or <think> blocks in the content."""
    parts = [message.get("reasoning_content") or ""]
    parts += [m.group(0).removeprefix("<think>").removesuffix("</think>") for m in _THINK.finditer(
        message.get("content") or "")]
    return "\n".join(p.strip() for p in parts if p and p.strip())


def visible_text(message: dict) -> str:
    return _THINK.sub("", message.get("content") or "").strip()


class ChatService:
    def __init__(self, settings: Settings, tools: list[dict] | None = None, model_call: ModelCall | None = None,
                 tool_runner: RunTool | None = None, record: Record | None = None,
                 load: Callable[[str], dict | None] | None = None, ledger: Path | None = None):
        self.settings = settings
        self.tools = tools or []
        self.model_call = model_call or self.http_call
        self.run_tool = tool_runner or run_tool
        self.record = record or record_answer
        self.load = load or load_session
        self.ledger = ledger or settings.store_dir / "chat" / "model_calls.jsonl"
        self._claim: dict | None = None          # {"session_id", "since", "started"}: the one live turn
        self.histories: dict[str, list[dict]] = {}
        self.subjects: dict[str, str | None] = {}      # role per chat session (round 2 W3)
        self.owners: dict[str, str | None] = {}        # gateway user per chat session (None in auth mode none)
        self.tool_calls: dict[str, int] = {}

    # ---------- configuration ----------

    @property
    def enabled(self) -> bool:
        s = self.settings
        return bool(s.chat.enabled and s.chat.configured and s.chat.api_key)

    def reason(self) -> str | None:
        s = self.settings
        if not s.chat.enabled:
            return "live chat is off (KB_CORE_CHAT_ENABLED)"
        if not s.chat.api_key:
            return f"the model key is not set ({s.chat.api_key_var})"
        return None

    def status(self) -> dict:
        return {"contract": "v1", "enabled": self.enabled, "reason": None if self.enabled else self.reason(),
                "model": self.settings.chat.model if self.enabled else None,
                "max_tool_calls": self.settings.chat_max_tool_calls, "busy": self.busy,
                "calls_used": self.calls_used(), "budget_calls": self.settings.chat_budget_calls}

    def set_tools(self, mcp_tools) -> None:
        """Function-calling tool specs from the MCP server's tool list (same names, descriptions and schemas)."""
        self.tools = [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                                                        "parameters": t.input_schema}} for t in mcp_tools]

    # ---------- model calls ----------

    async def http_call(self, payload: dict) -> dict:
        """One chat-completions call to the chat endpoint (its CA bundle; HTTPS_PROXY / NO_PROXY honoured)."""
        e = self.settings.chat
        async with httpx.AsyncClient(**e.httpx_options()) as client:
            r = await client.post(f"{e.base_url}/chat/completions", json=payload,
                                  headers={"Authorization": f"Bearer {e.api_key}"})
        if r.status_code != 200:
            raise ApiError("INTERNAL", f"model API returned HTTP {r.status_code}", model_status=r.status_code)
        return r.json()

    def calls_used(self) -> int:
        if not self.ledger.exists():
            return 0
        with self.ledger.open() as f:
            return sum(1 for line in f if line.strip())

    def _check_budget(self) -> None:
        budget = self.settings.chat_budget_calls
        if budget is not None and self.calls_used() >= budget:
            raise ApiError("LAYER_UNAVAILABLE", f"model call budget reached ({budget} calls)",
                           available_layers=["replay"])

    def _log_call(self, session_id: str, resp: dict | None, ms: int, error: str | None = None) -> None:
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        usage = (resp or {}).get("usage") or {}
        choice = ((resp or {}).get("choices") or [{}])[0]
        with self.ledger.open("a") as f:
            f.write(json.dumps({"at": datetime.now(UTC).isoformat(), "session_id": session_id,
                                "model": self.settings.chat.model, "ms": ms,
                                "finish_reason": choice.get("finish_reason"), "error": error,
                                "prompt_tokens": usage.get("prompt_tokens"),
                                "completion_tokens": usage.get("completion_tokens")}) + "\n")

    # ---------- sessions ----------

    @property
    def busy(self) -> bool:
        c = self._claim
        if c and not c["started"] and time.monotonic() - c["since"] > STALE_CLAIM_S:
            self._claim = None                   # the client went away before its stream started
        return self._claim is not None

    def release(self, claim: dict | None = None) -> None:
        if claim is None or self._claim is claim:
            self._claim = None

    async def prepare(self, message, session_id: str | None, subject: str | None = None,
                      user: str | None = None) -> str:
        """Validate a request and claim the live slot before streaming starts (errors become normal JSON
        responses); returns the session id. The caller must run run_turn, which releases the claim."""
        if not self.enabled:
            raise ApiError("LAYER_UNAVAILABLE", self.reason() or "live chat is not available",
                           available_layers=["replay"])
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
            raise ApiError("INVALID_PARAM", "message must be a string of 1-2000 characters", param="message")
        if session_id is not None and not (isinstance(session_id, str) and re.fullmatch(r"chat_[0-9a-f]{32}",
                                                                                           session_id)):
            raise ApiError("INVALID_PARAM", "session_id must be a chat session id returned earlier", param="session_id")
        from kb_core.access.policy import load_roles

        if subject is not None and subject not in load_roles():
            raise ApiError("INVALID_PARAM", f"unknown subject {subject!r}", param="subject", allowed=sorted(load_roles()))
        if session_id is not None and session_id in self.owners and self.owners[session_id] != user:
            raise ApiError("NOT_FOUND", f"no chat session {session_id}")      # another user's: as if missing
        if session_id is not None and session_id in self.subjects and self.subjects[session_id] != subject:
            raise ApiError("INVALID_PARAM", "a chat session keeps the subject it started with; start a new session",
                           param="subject")
        if self.busy:                            # check and claim with no await in between: atomic in the event loop
            raise ApiError("LAYER_UNAVAILABLE", "another live chat is running; try again when it finishes",
                           available_layers=["replay"])
        self._claim = {"session_id": session_id, "since": time.monotonic(), "started": False}
        try:
            if session_id is None:
                session_id = f"chat_{uuid.uuid4().hex}"
                self.histories[session_id], self.tool_calls[session_id] = [], 0
            elif session_id not in self.histories:
                out = await run_in_threadpool(self.load, session_id)
                if out is None or out.get("user") != user:     # another user's session: as if missing
                    raise ApiError("NOT_FOUND", f"no chat session {session_id}")
                if out.get("subject") != subject:
                    raise ApiError("INVALID_PARAM", "a chat session keeps the subject it started with; start a new "
                                   "session", param="subject")
                self.histories[session_id] = out.get("history") or []
                self.tool_calls[session_id] = int(out.get("session_tool_calls") or 0)
        except BaseException:
            self.release()
            raise
        self.subjects.setdefault(session_id, subject)
        self.owners.setdefault(session_id, user)
        self._claim["session_id"] = session_id
        return session_id

    # ---------- one turn ----------

    async def run_turn(self, message: str, session_id: str) -> AsyncIterator[str]:
        """One user message -> tool calls -> final answer, as SSE events: session, thinking, text, tool_call,
        tool_result, answer (always last) and error (before answer, when the turn failed)."""
        s = self.settings
        limit = s.chat_max_tool_calls
        claim = self._claim if self._claim and self._claim["session_id"] == session_id else None
        if claim is not None:
            claim["started"] = True
        try:
            started, t0 = datetime.now(UTC), time.perf_counter()
            history = self.histories[session_id]
            t = texts()
            system = {"role": "system", "content": t["instructions"] + "\n" + t["rules"] + SYSTEM_EXTRA}
            turn_start = len(history)
            history.append({"role": "user", "content": message})
            model_calls, usage, steps = 0, {"prompt_tokens": 0, "completion_tokens": 0}, []
            answer, finish, err, completed, disconnected = "", None, None, False, True
            number_check: dict | None = None
            turn_messages: list[dict] = []

            def outcome() -> dict:
                return {"model": s.chat.model, "answer": answer, "finish_reason": finish, "model_calls": model_calls,
                        "usage": usage, "steps": steps, "turn_tool_calls": len(steps),
                        "session_tool_calls": self.tool_calls[session_id], "number_check": number_check,
                        "turn_messages": turn_messages, "history": history, "completed": completed, "error": err,
                        "subject": self.subjects.get(session_id), "user": self.owners.get(session_id)}

            try:
                yield sse("session", {"session_id": session_id, "model": s.chat.model,
                                      "tool_calls_used": self.tool_calls[session_id], "max_tool_calls": limit})
                try:
                    while True:
                        if model_calls >= limit + 2:
                            err = f"no final answer after {model_calls} model calls in this turn"
                            break
                        self._check_budget()
                        payload = {"model": s.chat.model, "max_tokens": s.chat_max_tokens, "tools": self.tools,
                                   "messages": [system, *history]}
                        c0 = time.perf_counter()
                        try:
                            resp = await self.model_call(payload)
                            msg = resp["choices"][0]["message"]
                            if not isinstance(msg, dict):
                                raise ValueError("model response has no message object")
                        except Exception as e:  # noqa: BLE001 - a failed call may still be billed: record it
                            self._log_call(session_id, None, int((time.perf_counter() - c0) * 1000),
                                           error=getattr(e, "code", type(e).__name__))
                            raise
                        self._log_call(session_id, resp, int((time.perf_counter() - c0) * 1000))
                        model_calls += 1
                        for k in usage:
                            usage[k] += int((resp.get("usage") or {}).get(k) or 0)
                        finish = resp["choices"][0].get("finish_reason")
                        history.append({**msg, "role": "assistant"})     # kept as returned, reasoning included
                        thought = thinking_of(msg)
                        if thought:
                            yield sse("thinking", {"text": thought[:600]})
                        calls = msg.get("tool_calls") or []
                        text = visible_text(msg)
                        if finish == "length":
                            answer, err = text, "the model output was cut off (max tokens); this turn is discarded"
                            break
                        if not calls:
                            answer, completed = text, True
                            break
                        if text:
                            yield sse("text", {"text": text})
                        for call in calls:
                            async for event in self._tool_call(call, session_id, steps, history):
                                yield event
                    if completed:
                        number_check = check_numbers(answer, evidence_from_tool_results(
                            [m.get("content") or "" for m in history if m.get("role") == "tool"]))
                except ApiError as e:
                    err = f"{e.code}: {e.message}"
                except Exception as e:  # noqa: BLE001 - timeouts, connection failures, malformed responses
                    log.exception("chat turn failed")
                    err = f"INTERNAL: {type(e).__name__}"
                disconnected = False
            finally:
                turn_messages = list(history[turn_start:])
                if not completed:
                    del history[turn_start:]
                if disconnected:
                    # closed (aclose) or cancelled (Starlette on disconnect): shield the write from the cancellation
                    err = err or "client disconnected before the turn ended"
                    with anyio.CancelScope(shield=True), contextlib.suppress(Exception):
                        await run_in_threadpool(self.record, session_id, started, _ms(t0), message, outcome(),
                                                "error", "DISCONNECTED")
            try:
                trace_id = await run_in_threadpool(self.record, session_id, started, _ms(t0), message, outcome(),
                                                   "error" if err else "ok", "MODEL_ERROR" if err else None)
            except Exception as e:  # noqa: BLE001 - the client still gets error and answer
                log.exception("could not record agent.answer")
                trace_id = None
                err = (err + "; " if err else "") + f"the answer could not be recorded ({type(e).__name__}); this " \
                      "session cannot be continued after a restart"
            if err:
                yield sse("error", {"message": err, "trace_id": trace_id, "session_id": session_id})
            yield sse("answer", {"session_id": session_id, "answer": answer, "trace_id": trace_id,
                                 "model_calls": model_calls, "tool_calls": len(steps),
                                 "session_tool_calls": self.tool_calls[session_id], "usage": usage,
                                 "number_check": number_check, "error": err})
        finally:
            if claim is not None:
                self.release(claim)

    async def _tool_call(self, call: dict, session_id: str, steps: list, history: list) -> AsyncIterator[str]:
        limit = self.settings.chat_max_tool_calls
        call_id = call.get("id")
        fn = call.get("function") or {}
        name = fn.get("name")
        if not call_id:
            raise ValueError("tool call without id")

        def reply(content: str) -> None:
            history.append({"role": "tool", "tool_call_id": call_id, "content": content})

        if self.tool_calls[session_id] >= limit:
            reply(f"This session has reached its limit of {limit} tool calls. Answer from what you have already "
                  "read and say what could not be verified.")
            yield sse("tool_result", {"tool": name, "skipped": True, "reason": "limit"})
            return
        try:
            args = json.loads(fn.get("arguments") or "{}")
            if not isinstance(args, dict):
                raise ValueError
        except ValueError:
            reply("The arguments were not a JSON object; call the tool again with valid JSON arguments.")
            yield sse("tool_result", {"tool": name, "skipped": True, "reason": "invalid arguments"})
            return
        self.tool_calls[session_id] += 1
        n = self.tool_calls[session_id]
        yield sse("tool_call", {"n": n, "tool": name, "input": args})
        t0 = time.perf_counter()
        subject, user = self.subjects.get(session_id), self.owners.get(session_id)
        status, body = await run_in_threadpool(self.run_tool, name, args, session_id,
                                               **({"subject": subject} if subject else {}),
                                               **({"user": user} if user else {}))
        ms = _ms(t0)
        summary = summarize(name, status, body)
        steps.append({"n": n, "tool": name, "input": args, "status": status, "trace_id": body.get("trace_id"),
                      "ms": ms, **summary})
        yield sse("tool_result", {"n": n, "tool": name, "status": status, "trace_id": body.get("trace_id"), "ms": ms,
                                  **summary})
        reply(tool_text(name, status, body) + f"\n\n({limit - n} tool calls left in this session)")


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def summarize(tool: str, status: int, body: dict) -> dict:
    """What the UI shows for a step (the full result is in that call's trace event)."""
    if status != 200:
        return {"error": (body.get("error") or {}).get("code")}
    res = body.get("results") or []
    gaps = [g.get("code") for g in body.get("gaps") or []]
    out: dict = {"count": len(res), "gaps": gaps}
    if tool == "search" and res:
        tiers: dict[str, int] = {}
        for r in res:
            tiers[r.get("tier")] = tiers.get(r.get("tier"), 0) + 1
        src = res[0].get("source") or {}
        out.update(tiers=tiers, top={"title": res[0].get("title"), "doc_id": src.get("doc_id"),
                                     "page_range": src.get("page_range")})
    elif tool == "get_metric_series":
        out.update(concept_id=((body.get("scope") or {}).get("concept") or {}).get("concept_id"),
                   years=sorted({r.get("fiscal_year") for r in res if r.get("fiscal_year") is not None}))
    elif tool == "read":
        pages = [r["page_no"] for r in res if "page_no" in r]
        docs = (body.get("scope") or {}).get("docs") or [{}]
        out.update(doc_id=docs[0].get("doc_id"), pages=[min(pages), max(pages)] if pages else None)
    return out
