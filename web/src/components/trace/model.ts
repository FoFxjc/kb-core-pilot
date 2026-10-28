// Pure helpers for the retrieval trace view: per-route rank tables, coverage gate classification and row summaries.
import type { Gap, TraceDetail } from '../../api/client';

export type CoverageStatus = 'pass' | 'fail';

/** The coverage gate blocks a candidate whose coverage is below the threshold; equal to the threshold passes. */
export function coverageStatus(coverage: number, threshold: number): CoverageStatus {
  return coverage < threshold ? 'fail' : 'pass';
}

export interface RankRow {
  nodeId: string;
  /** Rank (1-based) of the node in each route, null when the route did not return it. */
  ranks: Record<string, number | null>;
  /** Best (lowest) rank over all routes; used for ordering. */
  best: number;
  inResults: boolean;
  /** Routes in which the coverage gate blocked this node, with the coverage it had. */
  blocked: Record<string, number>;
}

export interface RankTable {
  group: string;
  routes: string[];
  rows: RankRow[];
}

/** One table per group: rows are the node ids found by any route, columns the routes, cells the rank in that route.
 * Rows are ordered by best rank, then by how many routes found the node, then by node id. */
export function buildRankTables(
  routes: TraceDetail['routes'],
  resultNodeIds: Iterable<string>,
  dropped?: TraceDetail['coverage_dropped'],
): RankTable[] {
  if (!routes) return [];
  const inResults = new Set(resultNodeIds);
  return Object.entries(routes).map(([group, byRoute]) => {
    const routeKeys = Object.keys(byRoute);
    const rows = new Map<string, RankRow>();
    for (const route of routeKeys) {
      byRoute[route].forEach((nodeId, i) => {
        let row = rows.get(nodeId);
        if (!row) {
          row = { nodeId, ranks: Object.fromEntries(routeKeys.map((r) => [r, null])), best: Infinity,
            inResults: inResults.has(nodeId), blocked: {} };
          rows.set(nodeId, row);
        }
        if (row.ranks[route] === null) row.ranks[route] = i + 1;
        row.best = Math.min(row.best, i + 1);
      });
    }
    for (const [route, pairs] of Object.entries(dropped?.[group] ?? {})) {
      for (const [nodeId, cov] of pairs) {
        const row = rows.get(nodeId);
        if (row) row.blocked[route] = cov;
      }
    }
    const hits = (r: RankRow) => Object.values(r.ranks).filter((v) => v !== null).length;
    const sorted = [...rows.values()].sort(
      (a, b) => a.best - b.best || hits(b) - hits(a) || a.nodeId.localeCompare(b.nodeId));
    return { group, routes: routeKeys, rows: sorted };
  });
}

export interface CoverageRow {
  group: string | null;
  route: string;
  nodeId: string;
  coverage: number;
  status: CoverageStatus;
}

/** Coverage decisions: candidates blocked per group and route (`coverage_dropped`) and the coverage of the
 * candidates that were kept (`tier_decisions[*].coverage`), each classified against the threshold. */
export function coverageRows(detail: TraceDetail | undefined): { threshold: number | null; rows: CoverageRow[] } {
  const threshold = typeof detail?.coverage_threshold === 'number' ? detail.coverage_threshold : null;
  const rows: CoverageRow[] = [];
  const classify = (c: number): CoverageStatus => (threshold === null ? 'pass' : coverageStatus(c, threshold));
  for (const [group, byRoute] of Object.entries(detail?.coverage_dropped ?? {})) {
    for (const [route, pairs] of Object.entries(byRoute)) {
      for (const [nodeId, coverage] of pairs) rows.push({ group, route, nodeId, coverage, status: classify(coverage) });
    }
  }
  for (const [nodeId, d] of Object.entries(detail?.tier_decisions ?? {})) {
    for (const [route, coverage] of Object.entries(d.coverage ?? {})) {
      rows.push({ group: null, route, nodeId, coverage, status: classify(coverage) });
    }
  }
  return { threshold, rows };
}

/** The query, or the main params, of a call in one line. */
export function summarizeInput(tool: string, input: Record<string, unknown>): string {
  const s = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v));
  const pick = (keys: string[]) =>
    keys.filter((k) => input[k] !== undefined && input[k] !== null).map((k) => `${k}=${s(input[k])}`).join(' ');
  if (typeof input.query === 'string') {
    const rest = pick(['fiscal_years', 'lang', 'doc_ids']);
    return rest ? `${input.query} (${rest})` : input.query;
  }
  if (typeof input.term === 'string') return input.term;
  const main = tool === 'read' ? pick(['doc_id', 'page_range', 'node_id'])
    : tool === 'browse' ? pick(['doc_id', 'node_id', 'depth'])
    : tool === 'get_metric_series' ? pick(['concept_id', 'fiscal_years', 'entity'])
    : '';
  return main || JSON.stringify(input);
}

export function gapCodes(gaps: Gap[] | null | undefined): string[] {
  return [...new Set((gaps ?? []).map((g) => g.code))];
}

const pad = (n: number) => String(n).padStart(2, '0');

/** Local time as YYYY-MM-DD HH:MM:SS. */
export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** First physical page of a compact result (search and facts carry page_range; read carries page_no). */
export function firstPage(r: Record<string, unknown>): number | undefined {
  const pr = r.page_range;
  if (Array.isArray(pr) && typeof pr[0] === 'number') return pr[0];
  if (typeof r.page_no === 'number') return r.page_no;
  return undefined;
}

export function pageText(r: Record<string, unknown>): string {
  const pr = r.page_range;
  if (Array.isArray(pr) && pr.length === 2) return pr[0] === pr[1] ? `${pr[0]}` : `${pr[0]}-${pr[1]}`;
  if (typeof r.page_no === 'number') return `${r.page_no}`;
  return '';
}

/** The page route records its hits as a Python tuple repr, e.g. "('ocbc-group_ar_2024_en', 100)"; returns the
 * document and page, or null for an ordinary node id. */
export function parsePageKey(key: string): { docId: string; page: number } | null {
  const m = /^\('([^']+)', (\d+)\)$/.exec(key);
  return m ? { docId: m[1], page: Number(m[2]) } : null;
}
