// View 1: recorded sessions and their answers (replay), and live chat when the server has it configured; tool calls
// with tier badges; citations link to the document view.
import { useMemo } from 'react';
import { api, type Replay } from '../api/client';
import { GapList, ToolCalls, type SessionCall } from '../components/chat/ToolCalls';
import { Markdown } from '../components/chat/Markdown';
import { LiveChat } from '../components/chat/LiveChat';
import { ErrorBanner, Link, Loading } from '../components/Shared';
import { useAsync } from '../lib/hooks';
import '../components/chat/chat.css';

function ModeSwitch({ live }: { live: boolean }) {
  const config = useAsync(() => api.config(), []);
  if (!config.data) return null;
  if (!config.data.live_chat) {
    return <div className="chat-mode" data-mode="replay">Replay of recorded sessions. Live chat is off.</div>;
  }
  return (
    <nav className="chat-modes" aria-label="Chat mode" data-mode={live ? 'live' : 'replay'}>
      <Link to={{ view: 'chat' }} className={live ? 'chat-mode-tab' : 'chat-mode-tab active'}>Replay</Link>
      <Link to={{ view: 'chat', live: true }} className={live ? 'chat-mode-tab active' : 'chat-mode-tab'}>Live</Link>
    </nav>
  );
}

function SessionList({ replays, selected }: { replays: Replay[]; selected: string }) {
  return (
    <nav className="chat-sessions panel" aria-label="Recorded sessions">
      <h2 className="chat-h">Sessions</h2>
      <ul>
        {replays.map((r) => (
          <li key={r.id}>
            <Link to={{ view: 'chat', replay: r.id }} className={r.id === selected ? 'chat-session active' : 'chat-session'}>
              <span className="mono">{r.id}</span>
              {r.run && <span className="muted chat-session-run">{r.run}</span>}
              <span className="muted chat-session-run">
                {Object.keys(r.questions).length} questions · {r.tool_calls.length} tool calls
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function SessionView({ replay }: { replay: Replay }) {
  const sid = replay.session_id;
  const session = useAsync(() => (sid ? api.session(sid) : Promise.resolve(null)), [sid]);
  const byTrace = useMemo(() => {
    if (!session.data) return null;
    return new Map(session.data.calls.map((c) => [c.trace_id, c as unknown as SessionCall]));
  }, [session.data]);

  return (
    <article className="chat-session-view" data-replay={replay.id}>
      <header className="chat-session-head">
        <h2 className="chat-h">{replay.id}</h2>
        <span className="muted">
          {replay.run ?? ''}{sid ? ` · session ${sid}` : ' · no session id recorded'}
        </span>
      </header>

      <section className="chat-section">
        <h3 className="chat-h">Questions</h3>
        {Object.entries(replay.questions).map(([key, text]) => (
          <div key={key} className="chat-msg chat-user" data-question={key}>
            <span className="chat-who">User · {key}</span>
            <div>{text}</div>
          </div>
        ))}
      </section>

      <section className="chat-section">
        <h3 className="chat-h">Tool calls</h3>
        <ErrorBanner error={session.error} />
        {session.loading && <Loading what="session results" />}
        <ToolCalls calls={replay.tool_calls} session={session.loading ? null : byTrace} />
      </section>

      <section className="chat-section">
        <h3 className="chat-h">Answer</h3>
        <div className="chat-msg chat-agent">
          <span className="chat-who">Agent</span>
          {replay.answer ? <Markdown text={replay.answer} /> : <p className="muted">No answer was recorded.</p>}
        </div>
      </section>

      <section className="chat-section">
        <h3 className="chat-h">Gaps</h3>
        {byTrace ? <GapList calls={replay.tool_calls} session={byTrace} />
          : !session.loading && <p className="muted">Gaps are not available without the session record.</p>}
      </section>
    </article>
  );
}

export function Chat({ replay, live = false, session }: { replay?: string; live?: boolean; session?: string }) {
  if (live) {
    return (
      <section className="view chat" data-view="chat">
        <ModeSwitch live />
        <div className="chat-main panel"><LiveChat key={session ?? 'new'} session={session} /></div>
      </section>
    );
  }
  return <ReplayChat replay={replay} />;
}

function ReplayChat({ replay }: { replay?: string }) {
  const replays = useAsync(() => api.replays(), []);
  const list = replays.data?.replays ?? [];
  const selected = replay ? list.find((r) => r.id === replay) : list[0];

  return (
    <section className="view chat" data-view="chat">
      <ModeSwitch live={false} />
      <ErrorBanner error={replays.error} />
      {replays.loading ? (
        <Loading what="recorded sessions" />
      ) : replays.error ? null : list.length === 0 ? (
        <p className="muted chat-empty">No recorded sessions yet.</p>
      ) : (
        <div className="chat-layout">
          <SessionList replays={list} selected={selected?.id ?? ''} />
          <div className="chat-main panel">
            {selected ? <SessionView key={selected.id} replay={selected} />
              : <p className="muted">No recorded session with id <code>{replay}</code>.</p>}
          </div>
        </div>
      )}
    </section>
  );
}
