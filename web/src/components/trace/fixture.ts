// A search trace shaped like a real `GET /v1/admin/traces/{id}` response (trimmed from "NPL ratio 2025").
import type { Trace } from '../../api/client';

export const SEARCH_TRACE: Trace = {
  trace_id: 'tr_fixture_search',
  tool: 'search',
  source: 'ui',
  session_id: null,
  started_at: '2026-10-27T04:21:00.000000+00:00',
  duration_ms: 87,
  status: 'ok',
  error: null,
  input: { query: 'NPL ratio 2025' },
  output: {
    results: [
      { rank: 1, tier: 'fact', doc_id: 'ar_2025_en', concept_id: 'npl_ratio', page_range: [98, 98], fiscal_year: 2025 },
      { rank: 2, tier: 'link', score: 0.016, doc_id: 'ar_2025_en', node_id: 'ar_2025_en:n1', page_range: [98, 100] },
      { rank: 3, tier: 'text', score: 0.012, doc_id: 'ar_2024_en', node_id: 'ar_2024_en:n7', page_range: [40, 40] },
    ],
    gaps: [{ code: 'tree_quality_low', severity: 'warn', detail: 'primary tree spot-check accuracy is below 85%',
      doc_id: 'ar_2023_en' }],
    scope: { docs: ['ar_2024_en', 'ar_2025_en'] },
    truncated: false,
    detail: {
      routes: {
        all: {
          concept: ['ar_2025_en:n1', 'ar_2024_en:n3'],
          title_tok: ['ar_2024_en:n3', 'ar_2025_en:n9'],
          summary_tok: ['ar_2024_en:n7', 'ar_2025_en:n1', 'ar_2025_en:n9'],
        },
      },
      coverage_threshold: 0.5,
      coverage_units: [{ id: 'npl_ratio', kind: 'alias' }],
      coverage_dropped: { all: { title_tok: [['ar_2024_en:n3', 0.0], ['ar_2025_en:n9', 0.36]] } },
      tier_decisions: {
        'ar_2025_en:n1': { tier: 'link', title_terms: [], coverage: {}, concepts: [{ concept_id: 'npl_ratio' }] },
        'ar_2024_en:n7': { tier: 'text', title_terms: ['npl'], coverage: { summary_tok: 1.0 }, concepts: [],
          demoted_link: [{ concept_id: 'npl_ratio' }] } as never,
      },
      queries: {
        'S1_node_title_bm25.v1': { size: 50, query: { bool: { must: [{ match: { title_tok: 'npl ratio' } }] } } },
        'M1_series.v1': { sql: 'SELECT * FROM fact.series WHERE concept_id = %(concept_id)s', params: { concept_id: 'npl_ratio' } },
      },
      ranking_version: 3,
    },
  },
};
