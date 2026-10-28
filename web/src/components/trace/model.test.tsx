import { describe, expect, it } from 'vitest';
import { buildRankTables, coverageRows, coverageStatus, firstPage, gapCodes, parsePageKey, summarizeInput } from './model';
import { SEARCH_TRACE } from './fixture';

const detail = SEARCH_TRACE.output.detail!;

describe('per-route rank table', () => {
  const [table] = buildRankTables(detail.routes, ['ar_2025_en:n1', 'ar_2024_en:n7'], detail.coverage_dropped);

  it('builds one table per group with the routes as columns', () => {
    expect(buildRankTables(detail.routes, [])).toHaveLength(1);
    expect(table.group).toBe('all');
    expect(table.routes).toEqual(['concept', 'title_tok', 'summary_tok']);
  });

  it('has one row per node found by any route, with its rank in each route', () => {
    const byId = Object.fromEntries(table.rows.map((r) => [r.nodeId, r]));
    expect(Object.keys(byId).sort()).toEqual(['ar_2024_en:n3', 'ar_2024_en:n7', 'ar_2025_en:n1', 'ar_2025_en:n9']);
    expect(byId['ar_2025_en:n1'].ranks).toEqual({ concept: 1, title_tok: null, summary_tok: 2 });
    expect(byId['ar_2024_en:n3'].ranks).toEqual({ concept: 2, title_tok: 1, summary_tok: null });
    expect(byId['ar_2025_en:n9'].ranks).toEqual({ concept: null, title_tok: 2, summary_tok: 3 });
  });

  it('orders rows by best rank, then by how many routes found them', () => {
    expect(table.rows.map((r) => r.nodeId)).toEqual(['ar_2024_en:n3', 'ar_2025_en:n1', 'ar_2024_en:n7', 'ar_2025_en:n9']);
  });

  it('marks the nodes that made it into the results and the cells blocked by the coverage gate', () => {
    expect(table.rows.filter((r) => r.inResults).map((r) => r.nodeId).sort()).toEqual(['ar_2024_en:n7', 'ar_2025_en:n1']);
    expect(table.rows.find((r) => r.nodeId === 'ar_2025_en:n9')!.blocked).toEqual({ title_tok: 0.36 });
  });

  it('returns nothing without routes', () => {
    expect(buildRankTables(undefined, [])).toEqual([]);
  });
});

describe('coverage gate', () => {
  it('fails strictly below the threshold and passes at or above it', () => {
    expect(coverageStatus(0.36, 0.5)).toBe('fail');
    expect(coverageStatus(0, 0.5)).toBe('fail');
    expect(coverageStatus(0.5, 0.5)).toBe('pass');
    expect(coverageStatus(1, 0.5)).toBe('pass');
  });

  it('classifies dropped candidates and kept coverage against the threshold', () => {
    const { threshold, rows } = coverageRows(detail);
    expect(threshold).toBe(0.5);
    expect(rows.map((r) => [r.nodeId, r.route, r.status])).toEqual([
      ['ar_2024_en:n3', 'title_tok', 'fail'],
      ['ar_2025_en:n9', 'title_tok', 'fail'],
      ['ar_2024_en:n7', 'summary_tok', 'pass'],
    ]);
    expect(rows[0].group).toBe('all');
    expect(rows[2].group).toBeNull();
  });
});

describe('row summaries', () => {
  it('shows the query or the main params', () => {
    expect(summarizeInput('search', { query: 'NPL ratio 2025' })).toBe('NPL ratio 2025');
    expect(summarizeInput('search', { query: 'net interest income', fiscal_years: [2024] })).toBe('net interest income (fiscal_years=[2024])');
    expect(summarizeInput('read', { doc_id: 'd', page_range: '98-98' })).toBe('doc_id=d page_range=98-98');
    expect(summarizeInput('resolve_concept', { term: 'liquidity coverage ratio' })).toBe('liquidity coverage ratio');
    expect(summarizeInput('get_metric_series', { concept_id: 'net_profit', fiscal_years: [2024, 2025] }))
      .toBe('concept_id=net_profit fiscal_years=[2024,2025]');
  });

  it('lists distinct gap codes and finds the first page', () => {
    expect(gapCodes([{ code: 'a' }, { code: 'b' }, { code: 'a' }])).toEqual(['a', 'b']);
    expect(gapCodes(null)).toEqual([]);
    expect(firstPage({ page_range: [98, 100] })).toBe(98);
    expect(firstPage({ page_no: 12 })).toBe(12);
    expect(firstPage({})).toBeUndefined();
  });

  it('reads page-route keys and leaves node ids alone', () => {
    expect(parsePageKey("('ocbc-group_ar_2024_en', 100)")).toEqual({ docId: 'ocbc-group_ar_2024_en', page: 100 });
    expect(parsePageKey('ocbc-group_ar_2024_en:regions:0274')).toBeNull();
  });
});
