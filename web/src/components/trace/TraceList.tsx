// The list of recent traced tool calls, filtered by tool and source, paged with next_cursor.
import { useEffect, useState } from 'react';
import { api, type TraceSummary } from '../../api/client';
import { ErrorBanner, Link, Loading } from '../Shared';
import { formatTime, gapCodes, summarizeInput } from './model';

export const TOOLS = ['search', 'read', 'browse', 'get_metric_series', 'resolve_concept'];
export const SOURCES = ['ui', 'chat', 'mcp', 'eval', 'http'];
const PAGE = 50;

interface ListState {
  traces: TraceSummary[];
  cursor: string | null;
  loading: boolean;
  error: unknown;
}

export function TraceList() {
  const [tool, setTool] = useState('');
  const [source, setSource] = useState('');
  const [state, setState] = useState<ListState>({ traces: [], cursor: null, loading: true, error: null });

  const load = (cursor: string | undefined, append: boolean, isLive: () => boolean = () => true) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    api.traces({ limit: PAGE, tool: tool || undefined, source: source || undefined, cursor }).then(
      (page) => isLive() && setState((s) => ({ traces: append ? [...s.traces, ...page.traces] : page.traces,
        cursor: page.next_cursor, loading: false, error: null })),
      (error) => isLive() && setState((s) => ({ ...s, loading: false, error })),
    );
  };

  useEffect(() => {
    let live = true;
    setState({ traces: [], cursor: null, loading: true, error: null });
    load(undefined, false, () => live);
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool, source]);

  return (
    <div className="tr-list">
      <div className="tr-filters">
        <label>
          Tool{' '}
          <select value={tool} onChange={(e) => setTool(e.target.value)} aria-label="Tool">
            <option value="">All</option>
            {TOOLS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          Source{' '}
          <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source">
            <option value="">All</option>
            {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>
      <ErrorBanner error={state.error} />
      {!state.loading && !state.error && state.traces.length === 0 && (
        <div className="tr-empty muted">No traced calls match these filters.</div>
      )}
      {state.traces.length > 0 && (
        <table className="grid tr-table">
          <thead>
            <tr>
              <th>Time</th><th>Tool</th><th>Source</th><th>Session</th><th>Query / params</th>
              <th className="num">Results</th><th>Gaps</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {state.traces.map((t) => (
              <tr key={t.trace_id} data-trace-id={t.trace_id}>
                <td className="mono nowrap">
                  <Link to={{ view: 'trace', traceId: t.trace_id }}>{formatTime(t.started_at)}</Link>
                </td>
                <td className="mono">{t.tool}</td>
                <td>{t.source}</td>
                <td className="mono tr-session" title={t.session_id ?? ''}>{t.session_id ?? <span className="muted">none</span>}</td>
                <td className="tr-query">
                  <Link to={{ view: 'trace', traceId: t.trace_id }}>{summarizeInput(t.tool, t.input)}</Link>
                </td>
                <td className="num">{t.n_results}</td>
                <td className="mono">{gapCodes(t.gaps).join(', ')}</td>
                <td><StatusText status={t.status} error={t.error} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {state.loading && <Loading what="traces" />}
      {!state.loading && state.cursor && (
        <button type="button" className="tr-more" onClick={() => load(state.cursor ?? undefined, true)}>
          More
        </button>
      )}
    </div>
  );
}

export function StatusText({ status, error }: { status: string; error?: string | null }) {
  return (
    <span className={status === 'ok' ? 'tr-ok' : 'tr-err'} title={error ?? undefined}>
      {status}
    </span>
  );
}
