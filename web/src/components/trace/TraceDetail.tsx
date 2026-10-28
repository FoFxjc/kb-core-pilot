// One traced call: request, results, gaps, per-route ranks, coverage gate, tier decisions and executed queries.
import { useState, type ReactNode } from 'react';
import type { Gap, Tier, Trace, TraceDetail as Detail } from '../../api/client';
import { Link, TierBadge } from '../Shared';
import { StatusText } from './TraceList';
import { buildRankTables, coverageRows, firstPage, formatTime, pageText, parsePageKey, type RankTable } from './model';

const TIERS: Tier[] = ['fact', 'link', 'structure', 'text'];
const SHOWN_DETAIL = new Set(['routes', 'queries', 'coverage_dropped', 'coverage_threshold', 'coverage_units',
  'tier_decisions']);
const ROW_LIMIT = 30;

type Concept = { concept_id?: string; method?: string; confidence?: number };
type Decision = { tier: Tier; title_terms?: string[]; coverage?: Record<string, number>; concepts?: unknown[];
  demoted_link?: unknown[] };

function Section({ id, title, children, note }: { id: string; title: string; children: ReactNode; note?: ReactNode }) {
  return (
    <section className="panel tr-section" aria-labelledby={`tr-${id}`} data-section={id}>
      <h2 id={`tr-${id}`}>{title}</h2>
      {note && <div className="tr-note muted">{note}</div>}
      {children}
    </section>
  );
}

const json = (v: unknown) => JSON.stringify(v, null, 2);
const fmtCov = (c: number) => c.toFixed(2);

export function TraceDetailView({ trace }: { trace: Trace }) {
  const out = trace.output ?? {};
  const detail = out.detail;
  const results = out.results ?? [];
  const resultNodeIds = results.map((r) => r.node_id).filter((v): v is string => typeof v === 'string');
  return (
    <div className="tr-detail">
      <Request trace={trace} />
      <Results trace={trace} />
      <Gaps gaps={out.gaps ?? []} />
      {detail?.routes && <RouteRanks tables={buildRankTables(detail.routes, resultNodeIds, detail.coverage_dropped)} />}
      {(detail?.coverage_threshold !== undefined || detail?.coverage_dropped) && <CoverageGate detail={detail} />}
      {detail?.tier_decisions && <TierDecisions detail={detail} />}
      <Queries queries={detail?.queries} />
      <OtherDetail trace={trace} />
    </div>
  );
}

function Request({ trace }: { trace: Trace }) {
  const err = trace.output?.error as { code?: string; message?: string } | undefined;
  return (
    <Section id="request" title="Request">
      <dl className="tr-dl">
        <dt>Tool</dt><dd className="mono">{trace.tool}</dd>
        <dt>Trace id</dt><dd className="mono">{trace.trace_id}</dd>
        <dt>Source</dt><dd>{trace.source}</dd>
        <dt>Session</dt><dd className="mono">{trace.session_id ?? <span className="muted">none</span>}</dd>
        <dt>Started</dt><dd className="mono">{formatTime(trace.started_at)}</dd>
        <dt>Duration</dt><dd>{trace.duration_ms} ms</dd>
        <dt>Status</dt><dd><StatusText status={trace.status} error={trace.error} /></dd>
        {(trace.error || err) && (
          <>
            <dt>Error</dt>
            <dd className="tr-err">{err?.code ? <span className="mono">{err.code}: </span> : null}{err?.message ?? trace.error}</dd>
          </>
        )}
      </dl>
      <h3>Input params</h3>
      <pre className="tr-pre">{json(trace.input)}</pre>
    </Section>
  );
}

function Results({ trace }: { trace: Trace }) {
  const results = trace.output?.results ?? [];
  const inputDoc = typeof trace.input.doc_id === 'string' ? trace.input.doc_id : undefined;
  return (
    <Section id="results" title="Results" note={trace.output?.truncated ? 'Truncated by the output budget.' : undefined}>
      {results.length === 0 ? <div className="muted">No results.</div> : (
        <table className="grid tr-table">
          <thead>
            <tr><th className="num">Rank</th><th>Tier</th><th>doc_id</th><th>node_id / item</th><th>Pages</th></tr>
          </thead>
          <tbody>
            {results.map((r, i) => {
              const docId = typeof r.doc_id === 'string' ? r.doc_id : inputDoc;
              const page = firstPage(r);
              const tier = TIERS.includes(r.tier as Tier) ? (r.tier as Tier) : null;
              const item = (r.node_id ?? r.concept_id ?? (r.page_no !== undefined ? `page ${r.page_no}` : '')) as string;
              const extra = r.fiscal_year !== undefined && !r.node_id ? ` (FY${r.fiscal_year})` : '';
              return (
                <tr key={i} data-node-id={typeof r.node_id === 'string' ? r.node_id : undefined}>
                  <td className="num">{r.rank === null || r.rank === undefined ? '' : String(r.rank)}</td>
                  <td>{tier ? <TierBadge tier={tier} /> : <span className="muted">{String(r.tier ?? '')}</span>}</td>
                  <td className="mono">{docId ?? ''}</td>
                  <td className="mono">{item}{extra}</td>
                  <td>
                    {docId && page !== undefined
                      ? <Link to={{ view: 'document', docId, page }}>p. {pageText(r)}</Link>
                      : pageText(r)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Section>
  );
}

function Gaps({ gaps }: { gaps: Gap[] }) {
  return (
    <Section id="gaps" title="Gaps">
      {gaps.length === 0 ? <div className="muted">No gaps.</div> : (
        <table className="grid tr-table">
          <thead><tr><th>Code</th><th>Severity</th><th>Detail</th><th>doc_id</th></tr></thead>
          <tbody>
            {gaps.map((g, i) => (
              <tr key={i}>
                <td className="mono">{g.code}</td>
                <td className={g.severity ? `sev-${g.severity}` : undefined}>{g.severity ?? ''}</td>
                <td>{g.detail ?? ''}</td>
                <td className="mono">{g.doc_id ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

function RouteRanks({ tables }: { tables: RankTable[] }) {
  return (
    <Section id="routes" title="Per-route ranks"
      note="Rank of each candidate in each retrieval route. Highlighted rows made it into the results; struck cells were blocked by the coverage gate.">
      {tables.map((t) => <RankTableView key={t.group} table={t} />)}
    </Section>
  );
}

function RankTableView({ table }: { table: RankTable }) {
  const [all, setAll] = useState(false);
  const rows = all ? table.rows : table.rows.slice(0, ROW_LIMIT);
  const kept = table.rows.filter((r) => r.inResults).length;
  return (
    <div className="tr-group" data-group={table.group}>
      <h3>Group <span className="mono">{table.group}</span> <span className="muted">
        ({table.rows.length} candidates, {kept} in results)</span></h3>
      <div className="tr-scroll">
        <table className="grid tr-table tr-ranks">
          <thead>
            <tr>
              <th>node_id</th>
              <th>In results</th>
              {table.routes.map((r) => <th key={r} className="num mono">{r}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.nodeId} className={row.inResults ? 'tr-kept' : undefined} data-node-id={row.nodeId}>
                <td className="mono"><CandidateId id={row.nodeId} /></td>
                <td>{row.inResults ? 'yes' : ''}</td>
                {table.routes.map((r) => {
                  const rank = row.ranks[r];
                  const blocked = row.blocked[r];
                  return (
                    <td key={r} className={`num${blocked !== undefined ? ' tr-blocked' : ''}`}
                      title={blocked !== undefined ? `blocked by the coverage gate (coverage ${fmtCov(blocked)})` : undefined}>
                      {rank ?? ''}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.rows.length > ROW_LIMIT && (
        <button type="button" className="tr-more" onClick={() => setAll(!all)}>
          {all ? `Show first ${ROW_LIMIT}` : `Show all ${table.rows.length}`}
        </button>
      )}
    </div>
  );
}

/** A node id, or a page hit from the page route shown as a link to that page. */
function CandidateId({ id }: { id: string }) {
  const page = parsePageKey(id);
  if (!page) return <>{id}</>;
  return <Link to={{ view: 'document', docId: page.docId, page: page.page }}>{page.docId} page {page.page}</Link>;
}

function CoverageGate({ detail }: { detail: Detail }) {
  const { threshold, rows } = coverageRows(detail);
  const units = Array.isArray(detail.coverage_units) ? (detail.coverage_units as { id: string; kind?: string }[]) : [];
  const failed = rows.filter((r) => r.status === 'fail');
  const passed = rows.filter((r) => r.status === 'pass');
  const [all, setAll] = useState(false);
  const shown = [...failed, ...passed];
  const visible = all ? shown : shown.slice(0, ROW_LIMIT);
  return (
    <Section id="coverage" title="Coverage gate"
      note="A candidate passes when its coverage of the query units is at or above the threshold; below it is blocked.">
      <dl className="tr-dl">
        <dt>Threshold</dt><dd className="mono">{threshold ?? 'n/a'}</dd>
        <dt>Units</dt>
        <dd>{units.length === 0 ? <span className="muted">none</span> : units.map((u) => (
          <span key={u.id} className="tr-chip mono">{u.id}{u.kind ? <span className="muted"> {u.kind}</span> : null}</span>
        ))}</dd>
        <dt>Decisions</dt>
        <dd><span className="tr-pass">{passed.length} pass</span> · <span className="tr-fail">{failed.length} fail</span></dd>
      </dl>
      {rows.length > 0 && (
        <div className="tr-scroll">
          <table className="grid tr-table">
            <thead><tr><th>Status</th><th>Group</th><th>Route</th><th>node_id</th><th className="num">Coverage</th></tr></thead>
            <tbody>
              {visible.map((r, i) => (
                <tr key={i} data-status={r.status}>
                  <td><span className={r.status === 'pass' ? 'tr-pass' : 'tr-fail'}>{r.status}</span></td>
                  <td className="mono">{r.group ?? ''}</td>
                  <td className="mono">{r.route}</td>
                  <td className="mono">{r.nodeId}</td>
                  <td className="num mono">{fmtCov(r.coverage)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {shown.length > ROW_LIMIT && (
        <button type="button" className="tr-more" onClick={() => setAll(!all)}>
          {all ? `Show first ${ROW_LIMIT}` : `Show all ${shown.length}`}
        </button>
      )}
    </Section>
  );
}

const conceptIds = (list: unknown[] | undefined) =>
  (list ?? []).map((c) => (c as Concept).concept_id ?? JSON.stringify(c)).join(', ');

function TierDecisions({ detail }: { detail: Detail }) {
  const decisions = Object.entries((detail.tier_decisions ?? {}) as Record<string, Decision>);
  const threshold = typeof detail.coverage_threshold === 'number' ? detail.coverage_threshold : null;
  return (
    <Section id="tiers" title="Tier decisions">
      <table className="grid tr-table">
        <thead>
          <tr><th>node_id</th><th>Tier</th><th>Title terms</th><th>Coverage</th><th>Concepts</th><th>Demoted link</th></tr>
        </thead>
        <tbody>
          {decisions.map(([nodeId, d]) => (
            <tr key={nodeId} data-node-id={nodeId}>
              <td className="mono">{nodeId}</td>
              <td>{TIERS.includes(d.tier) ? <TierBadge tier={d.tier} /> : String(d.tier)}</td>
              <td className="mono">{(d.title_terms ?? []).join(', ')}</td>
              <td className="mono">
                {Object.entries(d.coverage ?? {}).map(([route, c]) => (
                  <div key={route} className={threshold !== null && c < threshold ? 'tr-fail' : undefined}>
                    {route}: {fmtCov(c)}
                  </div>
                ))}
              </td>
              <td className="mono">{conceptIds(d.concepts)}</td>
              <td className="mono">{conceptIds(d.demoted_link)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

function isSql(q: unknown): q is { sql: string; params?: unknown } {
  return typeof q === 'object' && q !== null && typeof (q as { sql?: unknown }).sql === 'string';
}

function Queries({ queries }: { queries: Record<string, unknown> | undefined }) {
  const entries = Object.entries(queries ?? {});
  return (
    <Section id="queries" title="Executed queries">
      {entries.length === 0 ? <div className="muted">No queries recorded.</div> : entries.map(([id, q]) => (
        <details key={id} className="tr-query-block" data-template={id}>
          <summary><span className="mono">{id}</span> <span className="muted">{isSql(q) ? 'SQL' : 'ES DSL'}</span></summary>
          {isSql(q) ? (
            <>
              <pre className="tr-pre">{q.sql}</pre>
              {q.params !== undefined && <pre className="tr-pre">{json(q.params)}</pre>}
            </>
          ) : <pre className="tr-pre">{json(q)}</pre>}
        </details>
      ))}
    </Section>
  );
}

function OtherDetail({ trace }: { trace: Trace }) {
  const rest = Object.entries(trace.output?.detail ?? {}).filter(([k]) => !SHOWN_DETAIL.has(k));
  const scope = trace.output?.scope;
  if (rest.length === 0 && !scope) return null;
  return (
    <Section id="other" title="Other detail">
      {scope && (
        <details className="tr-query-block">
          <summary className="mono">scope</summary>
          <pre className="tr-pre">{json(scope)}</pre>
        </details>
      )}
      {rest.map(([k, v]) => (
        <details key={k} className="tr-query-block">
          <summary className="mono">{k}</summary>
          <pre className="tr-pre">{json(v)}</pre>
        </details>
      ))}
    </Section>
  );
}
