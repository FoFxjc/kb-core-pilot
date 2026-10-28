import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SEARCH_TRACE } from '../components/trace/fixture';
import { TraceView } from './Trace';

function mockFetch(handler: (url: string) => { status: number; body: unknown }) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const { status, body } = handler(String(input));
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const section = (name: string) => screen.getByRole('region', { name });

describe('TraceView with a trace id', () => {
  it('renders every section of a search trace', async () => {
    mockFetch(() => ({ status: 200, body: SEARCH_TRACE }));
    render(<TraceView traceId="tr_fixture_search" />);
    await screen.findByRole('region', { name: 'Request' });
    for (const name of ['Request', 'Results', 'Gaps', 'Per-route ranks', 'Coverage gate', 'Tier decisions',
      'Executed queries']) expect(section(name)).toBeTruthy();

    expect(within(section('Request')).getByText(/"query": "NPL ratio 2025"/)).toBeTruthy();
    expect(within(section('Request')).getByText('87 ms')).toBeTruthy();

    const link = within(section('Results')).getByRole('link', { name: 'p. 98-100' });
    expect(link.getAttribute('href')).toBe('/ui/docs/ar_2025_en/pages/98');
    expect(within(section('Results')).getAllByText('Fact').length).toBe(1);

    expect(within(section('Gaps')).getByText('tree_quality_low')).toBeTruthy();

    const ranks = section('Per-route ranks');
    expect(within(ranks).getByRole('columnheader', { name: 'title_tok' })).toBeTruthy();
    expect(ranks.querySelectorAll('tr.tr-kept')).toHaveLength(2);
    expect(ranks.querySelectorAll('td.tr-blocked')).toHaveLength(2);

    const gate = section('Coverage gate');
    expect(within(gate).getByText('1 pass')).toBeTruthy();
    expect(within(gate).getByText('2 fail')).toBeTruthy();

    const queries = section('Executed queries');
    expect(within(queries).getByText('S1_node_title_bm25.v1')).toBeTruthy();
    expect(within(queries).getByText('M1_series.v1')).toBeTruthy();
    expect(within(queries).getByText(/SELECT \* FROM fact.series/)).toBeTruthy();
  });

  it('hides the route and coverage sections for other tools', async () => {
    mockFetch(() => ({ status: 200, body: {
      ...SEARCH_TRACE, tool: 'read', input: { doc_id: 'd', page_range: '98-98' },
      output: { results: [{ rank: null, tier: 'text', page_no: 98 }], gaps: [],
        detail: { queries: { 'R1_pages_range.v1': { sql: 'SELECT 1', params: { doc_id: 'd' } } } } },
    } }));
    render(<TraceView traceId="tr_read" />);
    await screen.findByRole('region', { name: 'Request' });
    expect(screen.queryByRole('region', { name: 'Per-route ranks' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'Coverage gate' })).toBeNull();
    expect(within(section('Results')).getByRole('link', { name: 'p. 98' }).getAttribute('href')).toBe('/ui/docs/d/pages/98');
    expect(screen.getByText('R1_pages_range.v1')).toBeTruthy();
  });

  it('reports an unknown id', async () => {
    mockFetch(() => ({ status: 404, body: { contract: 'v1', error: { code: 'NOT_FOUND', message: "no trace 'tr_x'" } } }));
    render(<TraceView traceId="tr_x" />);
    expect((await screen.findByRole('alert')).textContent).toBe('No trace with id tr_x.');
  });

  it('reports other errors', async () => {
    mockFetch(() => ({ status: 500, body: { error: { code: 'INTERNAL', message: 'boom' } } }));
    render(<TraceView traceId="tr_y" />);
    expect((await screen.findByRole('alert')).textContent).toBe('boom');
  });
});

describe('TraceView list', () => {
  const summary = (id: string, query: string) => ({
    trace_id: id, tool: 'search', source: 'ui', session_id: 's1', started_at: '2026-10-27T04:21:00+00:00',
    duration_ms: 10, status: 'ok', error: null, input: { query }, gaps: [{ code: 'tree_quality_low' }], n_results: 13,
  });

  it('lists calls, filters by tool and pages with More', async () => {
    const fetchMock = mockFetch((url) => url.includes('cursor=c1')
      ? { status: 200, body: { traces: [summary('tr_2', 'second')], next_cursor: null } }
      : { status: 200, body: { traces: [summary('tr_1', 'NPL ratio 2025')], next_cursor: 'c1' } });
    render(<TraceView />);
    const link = await screen.findByRole('link', { name: 'NPL ratio 2025' });
    expect(link.getAttribute('href')).toBe('/ui/trace/tr_1');
    expect(screen.getByText('tree_quality_low')).toBeTruthy();
    expect(String(fetchMock.mock.calls[0][0])).toBe('/v1/admin/traces?limit=50');

    fireEvent.click(screen.getByRole('button', { name: 'More' }));
    await screen.findByRole('link', { name: 'second' });
    expect(screen.getByRole('link', { name: 'NPL ratio 2025' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'More' })).toBeNull();

    fireEvent.change(screen.getByLabelText('Tool'), { target: { value: 'read' } });
    await screen.findByRole('link', { name: 'NPL ratio 2025' });
    expect(String(fetchMock.mock.calls.at(-1)![0])).toBe('/v1/admin/traces?limit=50&tool=read');
  });

  it('shows the empty state', async () => {
    mockFetch(() => ({ status: 200, body: { traces: [], next_cursor: null } }));
    render(<TraceView />);
    expect(await screen.findByText('No traced calls match these filters.')).toBeTruthy();
  });
});
