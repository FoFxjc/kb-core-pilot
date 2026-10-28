// The tool calls of a recorded session, in order: tool, key params, a link to the trace, the result tiers, and gaps.
import type { Gap, Replay, Tier } from '../../api/client';
import { Link, TierBadge } from '../Shared';

/** A compact result as returned by GET /v1/admin/sessions/{id} (calls[].results). */
export interface CompactResult {
  tier: Tier;
  doc_id?: string;
  node_id?: string | null;
  concept_id?: string;
  page_range?: [number, number] | null;
  page_no?: number;
  fiscal_year?: number;
}

export interface SessionCall {
  trace_id: string;
  status?: string;
  gaps?: Gap[] | null;
  results?: CompactResult[];
}

const TIERS: Tier[] = ['fact', 'link', 'structure', 'text'];

function paramText(key: string, v: unknown): string {
  if (Array.isArray(v)) {
    if (key.endsWith('range') && v.length === 2) return v[0] === v[1] ? String(v[0]) : `${v[0]}-${v[1]}`;
    return v.map(String).join(', ');
  }
  if (v && typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function resultLabel(r: CompactResult): string {
  const where = r.page_range ? `p. ${r.page_range[0] === r.page_range[1] ? r.page_range[0] : r.page_range.join('-')}`
    : r.page_no !== undefined ? `p. ${r.page_no}` : '';
  return [r.doc_id, r.concept_id, r.fiscal_year, where].filter((x) => x !== undefined && x !== '').join(' ');
}

/** Every gap the session's calls returned, labelled with the call it came from. */
export function GapList({ calls, session }: { calls: Replay['tool_calls']; session: Map<string, SessionCall> }) {
  const rows = calls.flatMap((c, i) => (session.get(c.trace_id)?.gaps ?? []).map((g) => ({ n: i + 1, tool: c.tool, g })));
  if (rows.length === 0) return <p className="muted">The tool calls returned no gaps.</p>;
  return (
    <ul className="chat-gaps">
      {rows.map(({ n, tool, g }, i) => {
        const sev = g.severity ?? 'warn';
        return (
          <li key={i} data-severity={sev}>
            <span className={`chat-sev sev-${sev}`}>{sev}</span> <code>{g.code}</code>
            <span className="muted"> from call {n} ({tool})</span>
            {g.detail ? <div className="chat-gap-detail">{g.detail}</div> : null}
          </li>
        );
      })}
    </ul>
  );
}

export function ToolCalls({ calls, session }: { calls: Replay['tool_calls']; session: Map<string, SessionCall> | null }) {
  if (calls.length === 0) return <p className="muted">No tool calls were recorded.</p>;
  return (
    <ol className="chat-calls">
      {calls.map((c, i) => {
        const rec = session?.get(c.trace_id);
        const results = rec?.results ?? [];
        const counts = TIERS.map((t) => [t, results.filter((r) => r.tier === t).length] as const).filter(([, n]) => n > 0);
        return (
          <li key={c.trace_id || i} className="chat-call" data-trace={c.trace_id}>
            <div className="chat-call-head">
              <code className="chat-tool">{c.tool}</code>
              <span className="chat-params">
                {Object.entries(c.params).map(([k, v]) => (
                  <span key={k} className="chat-param"><span className="muted">{k}</span> {paramText(k, v)}</span>
                ))}
              </span>
              <Link to={{ view: 'trace', traceId: c.trace_id }} className="chat-trace-link">trace</Link>
            </div>
            <div className="chat-call-results">
              {!rec ? (
                <span className="muted">{session ? 'Not found in the session record' : 'Results not loaded'}</span>
              ) : results.length === 0 ? (
                <span className="muted">No results</span>
              ) : (
                <>
                  <span className="chat-tier-counts">
                    {counts.map(([t, n]) => <span key={t} className="chat-tier-count"><TierBadge tier={t} /> ×{n}</span>)}
                  </span>
                  <details className="chat-results">
                    <summary>{results.length} result{results.length === 1 ? '' : 's'}</summary>
                    <ul>
                      {results.map((r, j) => (
                        <li key={j}><TierBadge tier={r.tier} /> <span className="mono">{resultLabel(r)}</span></li>
                      ))}
                    </ul>
                  </details>
                </>
              )}
              {rec?.status === 'error' && <span className="sev-warn"> call failed</span>}
            </div>
            {rec?.gaps && rec.gaps.length > 0 && (
              <div className="chat-call-gaps muted">{rec.gaps.length} gap{rec.gaps.length === 1 ? '' : 's'} (see below)</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
