// Live chat: the server runs the agent over the same five tools (POST /v1/admin/chat, server-sent events). Each turn
// shows the tool calls as they happen, the answer with citations linking to the document view, and the number check:
// numbers in the answer that were not found in the tool results the agent received are listed, never hidden.
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, chatTurn, type ChatEvent, type ChatStatus, type NumberCheck } from '../../api/client';
import { href, navigate } from '../../lib/router';
import { ErrorBanner, Link, Loading } from '../Shared';
import { useAsync } from '../../lib/hooks';
import { Markdown } from './Markdown';

interface Step {
  n?: number;
  tool: string;
  input?: Record<string, unknown>;
  result?: Extract<ChatEvent, { event: 'tool_result' }>['data'];
}

interface Turn {
  question: string;
  steps: Step[];
  thinking: string[];
  notes: string[];
  answer: string | null;
  numberCheck: NumberCheck | null;
  error: string | null;
  traceId: string | null;
  done: boolean;
}

const newTurn = (question: string): Turn => ({ question, steps: [], thinking: [], notes: [], answer: null,
  numberCheck: null, error: null, traceId: null, done: false });

/** Fold one server event into the current turn. */
export function applyEvent(turn: Turn, e: ChatEvent): Turn {
  switch (e.event) {
    case 'thinking':
      return { ...turn, thinking: [...turn.thinking, e.data.text] };
    case 'text':
      return { ...turn, notes: [...turn.notes, e.data.text] };
    case 'tool_call':
      return { ...turn, steps: [...turn.steps, { n: e.data.n, tool: e.data.tool, input: e.data.input }] };
    case 'tool_result': {
      const steps = [...turn.steps];
      const at = e.data.n === undefined ? -1 : steps.findIndex((s) => s.n === e.data.n);
      if (at >= 0) steps[at] = { ...steps[at], result: e.data };
      else steps.push({ tool: e.data.tool, result: e.data });
      return { ...turn, steps };
    }
    case 'error':
      return { ...turn, error: e.data.message, traceId: e.data.trace_id };
    case 'answer':
      return { ...turn, answer: e.data.answer, numberCheck: e.data.number_check, traceId: e.data.trace_id,
        error: e.data.error ?? turn.error, done: true };
    default:
      return turn;
  }
}

function StepRow({ step, max }: { step: Step; max: number }) {
  const r = step.result;
  return (
    <li className="chat-call live-step" data-tool={step.tool}>
      <div className="chat-call-head">
        <span className="muted mono">{step.n ? `${step.n}/${max}` : '-'}</span>
        <span className="chat-tool">{step.tool}</span>
        {step.input && <span className="chat-params mono">{JSON.stringify(step.input)}</span>}
        {r?.trace_id && <Link to={{ view: 'trace', traceId: r.trace_id }} className="chat-trace-link">trace</Link>}
      </div>
      <div className="chat-call-results muted">
        {!r ? 'running...'
          : r.skipped ? `skipped (${r.reason})`
          : r.error ? `error ${r.error}`
          : `${r.count ?? 0} results${r.ms !== undefined ? ` · ${r.ms} ms` : ''}${r.gaps?.length ? ` · gaps: ${r.gaps.join(', ')}` : ''}`}
      </div>
    </li>
  );
}

export function NumberCheckPanel({ check }: { check: NumberCheck }) {
  if (check.checked === 0) return <p className="muted live-numbers">No numbers to check.</p>;
  if (check.unverified.length === 0) {
    return <p className="live-numbers live-ok">All {check.checked} numbers were found in the tool results.</p>;
  }
  return (
    <div className="live-numbers live-warn" role="status">
      <strong>{check.unverified.length} of {check.checked} numbers were not found in the tool results the agent
        received.</strong> They may be computed or wrong; check them against the cited pages.
      <ul>
        {check.unverified.map((x, i) => (
          <li key={i}><span className="mono live-num">{x.text}</span> <span className="muted">... {x.context} ...</span></li>
        ))}
      </ul>
    </div>
  );
}

function TurnView({ turn, max }: { turn: Turn; max: number }) {
  return (
    <div className="live-turn">
      <div className="chat-msg chat-user"><span className="chat-who">User</span><div>{turn.question}</div></div>
      {turn.thinking.length > 0 && (
        <details className="live-thinking"><summary>Thinking</summary>
          {turn.thinking.map((t, i) => <p key={i} className="muted">{t}</p>)}
        </details>
      )}
      {turn.steps.length > 0 && <ol className="chat-calls">{turn.steps.map((s, i) => <StepRow key={i} step={s} max={max} />)}</ol>}
      {turn.error && <div className="error-banner" role="alert">{turn.error}</div>}
      {turn.done && (
        <div className="chat-msg chat-agent">
          <span className="chat-who">Agent{turn.traceId ? ' · ' : ''}{turn.traceId && <span className="mono">{turn.traceId}</span>}</span>
          {turn.answer ? <Markdown text={turn.answer} /> : <p className="muted">No answer.</p>}
          {turn.numberCheck && <NumberCheckPanel check={turn.numberCheck} />}
        </div>
      )}
      {!turn.done && <Loading what="the agent" />}
    </div>
  );
}

export function LiveChat({ session }: { session?: string }) {
  const status = useAsync<ChatStatus>(() => api.chatStatus(), []);
  const [sessionId, setSessionId] = useState<string | null>(session ?? null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [used, setUsed] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  const s = status.data;
  if (status.loading) return <Loading what="live chat status" />;
  if (status.error || !s) return <ErrorBanner error={status.error} />;
  if (!s.enabled) {
    return <p className="muted chat-empty" data-live="off">Live chat is not available: {s.reason}</p>;
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true); setError(null); setText('');
    setTurns((t) => [...t, newTurn(message)]);
    abort.current = new AbortController();
    try {
      await chatTurn(message, sessionId, (ev) => {
        if (ev.event === 'session') {
          setSessionId(ev.data.session_id);
          setUsed(ev.data.tool_calls_used);
          if (ev.data.session_id !== sessionId) {
            window.history.replaceState(null, '', href({ view: 'chat', live: true, session: ev.data.session_id }));
          }
        }
        if (ev.event === 'answer') setUsed(ev.data.session_tool_calls);
        setTurns((t) => [...t.slice(0, -1), applyEvent(t[t.length - 1], ev)]);
      }, abort.current.signal);
    } catch (err) {
      setError(err);
      setTurns((t) => t.slice(0, -1));
      setText(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="live-chat" data-live="on">
      <header className="chat-session-head">
        <h2 className="chat-h">Live · {s.model}</h2>
        <span className="muted">
          {sessionId ? <span className="mono">{sessionId}</span> : 'new session'}
          {' · '}tool calls {used ?? 0}/{s.max_tool_calls}
        </span>
        <button type="button" className="live-new" disabled={busy}
          onClick={() => { setSessionId(null); setTurns([]); setUsed(null); navigate(href({ view: 'chat', live: true })); }}>
          New chat
        </button>
      </header>
      {session && turns.length === 0 && (
        <p className="muted">Continuing session <span className="mono">{session}</span>; earlier turns are in its traces.</p>
      )}
      {turns.map((t, i) => <TurnView key={i} turn={t} max={s.max_tool_calls} />)}
      <ErrorBanner error={error} />
      <form className="live-form" onSubmit={send}>
        <textarea aria-label="Question" value={text} rows={3} maxLength={2000} disabled={busy}
          placeholder="Ask about the documents, e.g. How did the NPL ratio change from 2024 to 2025?"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }} />
        <button type="submit" disabled={busy || !text.trim()}>{busy ? 'Answering...' : 'Ask'}</button>
      </form>
    </div>
  );
}
