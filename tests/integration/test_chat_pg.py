"""Live chat through the HTTP app against Postgres: SSE stream, agent.answer trace, restore after a restart.
The model is a fake that answers without tools, so Elasticsearch is not needed."""

import json

import pytest
from fastapi.testclient import TestClient

from kb_core.config import load_settings
from kb_core.pg.migrate import migrate
from tests.conftest import PG_DSN

pytestmark = [pytest.mark.pg]


async def fake_model(payload: dict) -> dict:
    question = payload["messages"][-1]["content"]
    return {"choices": [{"message": {"role": "assistant", "content": f"Echo: {question}. Total 123.4."},
                         "finish_reason": "stop"}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}


def make_client(tmp_path, **env):
    from kb_core.serve.app import create_app

    s = load_settings({"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": "http://127.0.0.1:1",
                       "KB_CORE_STORE_DIR": str(tmp_path), "KB_CORE_CHAT_ENABLED": "true",
                       "KB_CORE_LLM_BASE_URL": "https://llm.test/v1", "KB_CORE_LLM_MODEL": "m",
                       "KB_CORE_LLM_API_KEY": "secret-key", **env}, env_file=None)
    app = create_app(s)
    app.state.chat.model_call = fake_model
    return TestClient(app, base_url="http://127.0.0.1:8200")


def events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        head, data = block.split("\n", 1)
        out.append((head.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_live_chat_records_and_restores(pg_conn, tmp_path):
    migrate(pg_conn)
    with make_client(tmp_path) as c:
        assert c.get("/v1/admin/config").json()["live_chat"] is True
        root = c.get("/", follow_redirects=False)
        assert root.status_code == 307 and root.headers["location"] == "/ui/chat"
        status = c.get("/v1/admin/chat/status").json()
        assert status["enabled"] and status["model"] == "m" and "secret-key" not in json.dumps(status)
        assert c.post("/v1/admin/chat", json={"message": ""}).json()["error"]["code"] == "INVALID_PARAM"
        r = c.post("/v1/admin/chat", json={"message": "hello"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        ev = events(r.text)
        sid = ev[0][1]["session_id"]
        assert [k for k, _ in ev] == ["session", "answer"] and ev[-1][1]["number_check"]["unverified"][0]["text"] == "123.4"
        calls = c.get(f"/v1/admin/sessions/{sid}").json()["calls"]
        assert [x["tool"] for x in calls] == ["agent.answer"]
        stored = json.dumps(pg_conn.execute("SELECT input, output FROM quality.trace_event").fetchall())
        assert "secret-key" not in stored

    with make_client(tmp_path) as c:                     # a restart: the session comes back from the trace
        ev = events(c.post("/v1/admin/chat", json={"message": "again", "session_id": sid}).text)
        assert ev[0][1]["session_id"] == sid and ev[-1][1]["answer"].startswith("Echo: again")
        out = pg_conn.execute("SELECT output FROM quality.trace_event WHERE session_id = %s ORDER BY id DESC LIMIT 1",
                              (sid,)).fetchone()[0]
        assert [m["content"] for m in out["history"]][:2] == ["hello", "Echo: hello. Total 123.4."]
        missing = c.post("/v1/admin/chat", json={"message": "x", "session_id": "chat_" + "f" * 32})
        assert missing.status_code == 404


def test_chat_disabled_falls_back_to_replay(pg_conn, tmp_path):
    migrate(pg_conn)
    with make_client(tmp_path, KB_CORE_CHAT_ENABLED="false") as c:
        assert c.get("/v1/admin/config").json() == {"contract": "v1", "llm_enabled": False, "live_chat": False,
                                                     "mode": "replay", "role_picker": True}
        r = c.post("/v1/admin/chat", json={"message": "hello"})
        assert r.status_code == 409 and r.json()["error"]["code"] == "LAYER_UNAVAILABLE"
