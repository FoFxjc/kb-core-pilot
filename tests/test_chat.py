"""Live chat loop with a fake model, fake tools and an in-memory trace store (no network, no Postgres)."""

import asyncio
import json

import anyio

import pytest

from kb_core.config import load_settings
from kb_core.retrieval.core import ApiError
from kb_core.serve.chat import ChatService, thinking_of, tool_text, visible_text

BASE = {"KB_CORE_PG_DSN": "postgresql://unused", "KB_CORE_ES_URL": "http://unused",
        "KB_CORE_CHAT_ENABLED": "true", "KB_CORE_LLM_BASE_URL": "https://llm.test/v1", "KB_CORE_LLM_MODEL": "m",
        "KB_CORE_LLM_API_KEY": "k"}
TOOLS = [{"type": "function", "function": {"name": "search", "description": "d", "parameters": {"type": "object"}}}]
EVIDENCE = {"contract": "v1", "tool": "get_metric_series", "trace_id": "tr_1", "gaps": [],
            "results": [{"fiscal_year": 2025, "display": "7,587", "unit": "S$ million"}], "scope": {}}


def call(i: int, name: str = "search", args: dict | str | None = None) -> dict:
    raw = args if isinstance(args, str) else json.dumps(args or {"query": "net profit"})
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": raw}}


def reply(content: str | None = None, calls: list | None = None, finish: str | None = None, **extra) -> dict:
    msg = {"role": "assistant", "content": content, **extra}
    if calls:
        msg["tool_calls"] = calls
    return {"choices": [{"message": msg, "finish_reason": finish or ("tool_calls" if calls else "stop")}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


class Fake:
    def __init__(self, replies: list):
        self.replies, self.payloads, self.tool_runs, self.records, self.stored = list(replies), [], [], [], {}

    async def model(self, payload: dict) -> dict:
        self.payloads.append(json.loads(json.dumps(payload)))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def tool(self, name: str, args: dict, session_id: str, subject: str | None = None, user: str | None = None):
        self.tool_runs.append((name, args, session_id))
        self.subjects = getattr(self, "subjects", []) + [subject]
        self.users = getattr(self, "users", []) + [user]
        return 200, EVIDENCE

    def record(self, session_id, started, ms, message, out, status, error) -> str:
        self.records.append({"session_id": session_id, "message": message, "out": json.loads(json.dumps(out)),
                             "status": status, "error": error})
        self.stored[session_id] = json.loads(json.dumps(out))
        return f"tr_{len(self.records)}"


def service(fake: Fake, tmp_path, **env) -> ChatService:
    s = load_settings({**BASE, "KB_CORE_STORE_DIR": str(tmp_path), **env}, env_file=None)
    return ChatService(s, tools=TOOLS, model_call=fake.model, tool_runner=fake.tool, record=fake.record,
                       load=lambda sid: fake.stored.get(sid))


def run(svc: ChatService, message: str, session_id: str | None = None) -> list[tuple[str, dict]]:
    async def go():
        sid = await svc.prepare(message, session_id)
        return [e async for e in svc.run_turn(message, sid)]

    out = []
    for chunk in asyncio.run(go()):
        head, data = chunk.strip().split("\n", 1)
        out.append((head.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_tool_call_then_answer_with_number_check(tmp_path):
    fake = Fake([reply("<think>look it up</think>", [call(1)]),
                 reply("Net profit was S$7,587 million (S$7.6 billion); margin 9.99%.")])
    svc = service(fake, tmp_path)
    events = run(svc, "net profit 2025?")
    kinds = [k for k, _ in events]
    assert kinds == ["session", "thinking", "tool_call", "tool_result", "answer"]
    answer = events[-1][1]
    assert answer["answer"].startswith("Net profit was S$7,587") and answer["error"] is None
    nc = answer["number_check"]
    assert [x["text"] for x in nc["verified"]] == ["7,587", "7.6"] and [x["text"] for x in nc["unverified"]] == ["9.99"]
    assert fake.tool_runs == [("search", {"query": "net profit"}, answer["session_id"])]
    # the tool result tells the model how many calls are left; tools and system prompt are sent
    tool_msg = fake.payloads[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1" and "7 tool calls left" in tool_msg["content"]
    assert fake.payloads[0]["tools"] == TOOLS and fake.payloads[0]["messages"][0]["role"] == "system"
    assert "always write the whole answer in English" in fake.payloads[0]["messages"][0]["content"]
    rec = fake.records[-1]
    assert rec["status"] == "ok" and rec["out"]["completed"] and rec["out"]["session_tool_calls"] == 1
    assert [m["role"] for m in rec["out"]["history"]] == ["user", "assistant", "tool", "assistant"]
    assert svc.calls_used() == 2


def test_history_keeps_reasoning_and_next_turn_continues(tmp_path):
    fake = Fake([reply("<think>t1</think>A1", reasoning_details=[{"text": "t1"}]), reply("A2")])
    svc = service(fake, tmp_path)
    sid = run(svc, "q1")[-1][1]["session_id"]
    run(svc, "q2", sid)
    sent = fake.payloads[1]["messages"]
    assert sent[2] == {"role": "assistant", "content": "<think>t1</think>A1", "reasoning_details": [{"text": "t1"}]}
    assert sent[-1] == {"role": "user", "content": "q2"}


def test_session_restored_from_trace_after_restart(tmp_path):
    fake = Fake([reply("A1"), reply("A2")])
    sid = run(service(fake, tmp_path), "q1")[-1][1]["session_id"]
    fresh = service(fake, tmp_path)                       # a new process: nothing in memory
    events = run(fresh, "q2", sid)
    assert events[0][1]["session_id"] == sid and [m["content"] for m in fake.payloads[1]["messages"][1:]] == [
        "q1", "A1", "q2"]


def test_tool_limit_answers_every_call(tmp_path):
    fake = Fake([reply(None, [call(1), call(2)]), reply("Done.")])
    svc = service(fake, tmp_path, KB_CORE_CHAT_MAX_TOOL_CALLS="1")
    events = run(svc, "q")
    skipped = [d for k, d in events if k == "tool_result" and d.get("skipped")]
    assert len(fake.tool_runs) == 1 and skipped == [{"tool": "search", "skipped": True, "reason": "limit"}]
    tool_msgs = [m for m in fake.payloads[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2"] and "limit of 1" in tool_msgs[1]["content"]


def test_invalid_arguments_are_returned_to_the_model(tmp_path):
    fake = Fake([reply(None, [call(1, args="{not json")]), reply("ok")])
    events = run(service(fake, tmp_path), "q")
    assert fake.tool_runs == [] and ("tool_result", {"tool": "search", "skipped": True,
                                                     "reason": "invalid arguments"}) in events


@pytest.mark.parametrize("failure", [RuntimeError("boom"), ApiError("INTERNAL", "model API returned HTTP 500"),
                                     {"choices": []}])
def test_model_failure_rolls_back_the_turn(tmp_path, failure):
    fake = Fake([reply("A1"), failure])
    svc = service(fake, tmp_path)
    sid = run(svc, "q1")[-1][1]["session_id"]
    events = run(svc, "q2", sid)
    assert [k for k, _ in events][-2:] == ["error", "answer"]
    assert [m["content"] for m in svc.histories[sid]] == ["q1", "A1"]          # q2 rolled back
    assert fake.records[-1]["status"] == "error" and fake.records[-1]["out"]["turn_messages"][0]["content"] == "q2"
    assert svc.calls_used() == 2                                               # the failed call is in the ledger


def test_truncated_output_is_discarded(tmp_path):
    fake = Fake([reply("half an ans", finish="length")])
    svc = service(fake, tmp_path)
    events = run(svc, "q")
    assert events[-2][0] == "error" and "cut off" in events[-2][1]["message"]
    assert svc.histories[events[0][1]["session_id"]] == []


def test_disconnect_writes_answer_and_rolls_back(tmp_path):
    fake = Fake([reply(None, [call(1)]), reply("never")])
    svc = service(fake, tmp_path)
    async def go():
        sid = await svc.prepare("q", None)
        gen = svc.run_turn("q", sid)
        async for chunk in gen:
            if chunk.startswith("event: tool_call"):
                await gen.aclose()
                break

    asyncio.run(go())
    sid = fake.records[-1]["session_id"]
    assert fake.records[-1]["error"] == "DISCONNECTED" and fake.records[-1]["out"]["session_tool_calls"] == 1
    assert svc.histories[sid] == [] and not svc.busy


def test_cancelled_turn_still_records(tmp_path):
    """Starlette cancels the stream on disconnect (no aclose): the DISCONNECTED write must survive the cancel."""
    started = anyio.Event()

    async def slow_model(payload):
        started.set()
        await anyio.sleep(10)

    fake = Fake([])
    svc = service(fake, tmp_path)
    svc.model_call = slow_model

    async def go():
        sid = await svc.prepare("q", None)

        async def consume():
            async for _ in svc.run_turn("q", sid):
                pass

        async with anyio.create_task_group() as tg:
            tg.start_soon(consume)
            await started.wait()
            tg.cancel_scope.cancel()

    anyio.run(go)
    assert fake.records and fake.records[-1]["error"] == "DISCONNECTED" and not svc.busy


def test_second_request_is_refused_while_a_turn_is_claimed(tmp_path):
    fake = Fake([reply("A1")])
    svc = service(fake, tmp_path)

    async def go():
        sid = await svc.prepare("q1", None)
        with pytest.raises(ApiError) as e:
            await svc.prepare("q2", None)
        assert e.value.code == "LAYER_UNAVAILABLE" and svc.status()["busy"]
        [x async for x in svc.run_turn("q1", sid)]
        assert not svc.busy
        await svc.prepare("q3", sid)                      # free again

    asyncio.run(go())


def test_unstarted_claim_expires(tmp_path, monkeypatch):
    import kb_core.serve.chat as chat

    svc = service(Fake([]), tmp_path)
    asyncio.run(svc.prepare("q", None))
    assert svc.busy
    monkeypatch.setattr(chat, "STALE_CLAIM_S", -1)
    assert not svc.busy


def test_answer_event_even_when_the_trace_cannot_be_written(tmp_path):
    fake = Fake([reply("A1")])
    svc = service(fake, tmp_path)

    def broken(*args):
        raise OSError("postgres down")

    svc.record = broken
    events = run(svc, "q")
    assert [k for k, _ in events][-2:] == ["error", "answer"] and "could not be recorded" in events[-1][1]["error"]
    assert events[-1][1]["answer"] == "A1" and not svc.busy


def test_budget_stops_model_calls(tmp_path):
    fake = Fake([reply("A1"), reply("A2")])
    svc = service(fake, tmp_path, KB_CORE_CHAT_BUDGET_CALLS="1")
    run(svc, "q1")
    events = run(svc, "q2")
    assert "budget reached" in events[-2][1]["message"] and len(fake.payloads) == 1


def test_prepare_validates_before_streaming(tmp_path):
    fake = Fake([])
    svc = service(fake, tmp_path)
    for message, sid, code in [("", None, "INVALID_PARAM"), ("x" * 2001, None, "INVALID_PARAM"),
                               ("q", "not-a-session", "INVALID_PARAM"), ("q", "chat_" + "0" * 32, "NOT_FOUND")]:
        with pytest.raises(ApiError) as e:
            asyncio.run(svc.prepare(message, sid))
        assert e.value.code == code and not svc.busy
    off = service(fake, tmp_path, KB_CORE_CHAT_ENABLED="false")
    with pytest.raises(ApiError) as e:
        asyncio.run(off.prepare("q", None))
    assert e.value.code == "LAYER_UNAVAILABLE" and off.status()["reason"].startswith("live chat is off")
    nokey = service(fake, tmp_path, KB_CORE_LLM_API_KEY="")
    assert not nokey.enabled and "KB_CORE_LLM_API_KEY" in nokey.status()["reason"]


def test_key_never_shown(tmp_path):
    svc = service(Fake([]), tmp_path, KB_CORE_LLM_API_KEY="sekrit-123")
    assert svc.enabled and "sekrit-123" not in json.dumps(svc.status())
    assert "sekrit-123" not in repr(svc.settings) and svc.settings.redacted()["chat"]["api_key"] == "***"
    assert "sekrit-123" not in json.dumps(svc.settings.redacted(), default=str)


def test_key_variable_must_be_a_kb_core_name(tmp_path):
    from kb_core.config import ConfigError

    with pytest.raises(ConfigError):
        load_settings({**BASE, "KB_CORE_LLM_API_KEY_VAR": "OTHER_API_KEY"}, env_file=None)


def test_thinking_and_visible_text():
    msg = {"content": "<think>plan\n</think>\nAnswer", "reasoning_content": "r"}
    assert thinking_of(msg) == "r\nplan" and visible_text(msg) == "Answer"
    assert visible_text({"content": "<think>unclosed"}) == ""


def test_tool_text_drops_image_data_and_adds_outline():
    body = {"results": [{"page_no": 1, "image": {"mime": "image/png", "data_base64": "AAAA"}}]}
    assert "AAAA" not in tool_text("read", 200, body) and '"mime":"image/png"' in tool_text("read", 200, body)
    err = {"error": {"code": "UNKNOWN_DOC"}}
    assert tool_text("read", 404, err) == '{"error":{"code":"UNKNOWN_DOC"}}'


def test_the_chat_subject_reaches_every_tool_call_and_is_fixed_per_session(tmp_path):
    """Round 2 W3 T3.9: the dev role picker's subject is passed to every tool call of the session."""
    from kb_core.retrieval.core import ApiError

    fake = Fake([reply(None, [call(1)]), reply("NPL ratio was 0.9%.")])
    svc = service(fake, tmp_path)

    async def go():
        sid = await svc.prepare("NPL ratio?", None, subject="finance_analyst")
        out = [e async for e in svc.run_turn("NPL ratio?", sid)]
        with pytest.raises(ApiError) as e:
            await svc.prepare("again", sid, subject="public")
        return out, e.value.code

    _, code = asyncio.run(go())
    assert fake.subjects == ["finance_analyst"] and code == "INVALID_PARAM"


def test_a_chat_session_belongs_to_its_gateway_user(tmp_path):
    """Enterprise readiness B: tool calls carry the user; another user cannot continue the session, before or after a
    restart (the answer records the owner); the refusal looks like a missing session."""
    from kb_core.retrieval.core import ApiError

    fake = Fake([reply(None, [call(1)]), reply("NPL ratio was 0.9%."), reply("Still 0.9%.")])
    svc = service(fake, tmp_path)

    async def turn(service_, message, sid, user):
        sid = await service_.prepare(message, sid, subject="finance_analyst", user=user)
        return sid, [e async for e in service_.run_turn(message, sid)]

    async def refused(service_, sid, user):
        with pytest.raises(ApiError) as e:
            await service_.prepare("mine now", sid, subject="finance_analyst", user=user)
        return e.value.code

    sid, _ = asyncio.run(turn(svc, "NPL ratio?", None, "alice"))
    assert fake.users == ["alice"] and fake.stored[sid]["user"] == "alice"
    assert asyncio.run(refused(svc, sid, "bob")) == "NOT_FOUND"
    restarted = service(fake, tmp_path)
    assert asyncio.run(refused(restarted, sid, "bob")) == "NOT_FOUND"
    asyncio.run(turn(restarted, "and now?", sid, "alice"))          # the owner continues after the restart
