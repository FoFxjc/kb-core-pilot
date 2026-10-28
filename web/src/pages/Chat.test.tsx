import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Chat } from './Chat';

const REPLAY = {
  id: 'mcp_demo_round1', run: 'round-1 MCP demo', session_id: 'round1-demo',
  questions: { d2: 'How did the NPL ratio change from 2024 to 2025?', d4: 'What was the 2025 LCR?' },
  answer: '### 1. NPL\n\n**Unchanged.**\n\n- 0.9 (ocbc-group_ar_2025_en, physical page 98, printed page 96)\n' +
    '- (ocbc-group_ar_2025_en, physical page 99-100, printed page 97-98)',
  tool_calls: [
    { tool: 'get_metric_series', trace_id: 'tr_a', params: { concept_id: 'npl_ratio', fiscal_years: [2024, 2025] } },
    { tool: 'read', trace_id: 'tr_b', params: { doc_id: 'ocbc-group_ar_2025_en', page_range: [98, 100] } },
  ],
};
const SESSION = {
  session_id: 'round1-demo',
  calls: [
    { trace_id: 'tr_a', tool: 'get_metric_series', status: 'ok', input: {},
      gaps: [{ code: 'single_source', severity: 'info', detail: 'some years have only one source' }],
      results: [{ tier: 'fact', doc_id: 'ocbc-group_ar_2025_en', page_range: [98, 98] },
        { tier: 'fact', doc_id: 'ocbc-group_ar_2024_en', page_range: [98, 98] }] },
    { trace_id: 'tr_b', tool: 'read', status: 'ok', input: {}, gaps: [],
      results: [{ tier: 'text', page_no: 98 }] },
  ],
};

function mockFetch(routes: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const body = routes[url];
    if (body === undefined) return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: `no ${url}` } }),
      { status: 404 });
    return new Response(JSON.stringify(body), { status: 200 });
  }));
}

const CONFIG = { llm_enabled: false, live_chat: false, mode: 'replay' };

describe('Chat view', () => {
  beforeEach(() => window.history.replaceState(null, '', '/ui/chat'));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it('renders a recorded session: mode, questions, tool calls with badges, answer citations and gaps', async () => {
    mockFetch({ '/v1/admin/config': CONFIG, '/v1/admin/replays': { replays: [REPLAY] },
      '/v1/admin/sessions/round1-demo': SESSION });
    const { container } = render(<Chat />);
    expect(await screen.findByText('How did the NPL ratio change from 2024 to 2025?')).toBeTruthy();
    expect(screen.getByText('What was the 2025 LCR?')).toBeTruthy();
    expect(await screen.findByText(/Replay of recorded sessions/)).toBeTruthy();

    // Tool calls in order, each with a trace link and, once the session loads, tier badges.
    const calls = await vi.waitFor(() => {
      const items = container.querySelectorAll('.chat-call');
      expect(items[0].querySelector('[data-tier="fact"]')).not.toBeNull();
      return items;
    });
    expect(calls).toHaveLength(2);
    expect(within(calls[0] as HTMLElement).getByText('get_metric_series')).toBeTruthy();
    expect(within(calls[0] as HTMLElement).getByText('2024, 2025')).toBeTruthy();
    expect(within(calls[0] as HTMLElement).getByRole('link', { name: 'trace' }).getAttribute('href'))
      .toBe('/ui/trace/tr_a');
    expect(within(calls[1] as HTMLElement).getByText('98-100')).toBeTruthy();
    expect(calls[1].querySelector('[data-tier="text"]')).not.toBeNull();

    // Citations in the answer link to the document view at the physical page.
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/ui/docs/ocbc-group_ar_2025_en/pages/98');
    expect(hrefs).toContain('/ui/docs/ocbc-group_ar_2025_en/pages/99');
    expect(screen.getByRole('heading', { name: '1. NPL' })).toBeTruthy();

    // Gaps with severity.
    const gap = container.querySelector('.chat-gaps li') as HTMLElement;
    expect(gap.dataset.severity).toBe('info');
    expect(within(gap).getByText('single_source')).toBeTruthy();
  });

  it('selects the replay named in the route and reports an unknown one', async () => {
    const other = { ...REPLAY, id: 'other', session_id: null, questions: { q1: 'Other question' }, tool_calls: [] };
    mockFetch({ '/v1/admin/config': CONFIG, '/v1/admin/replays': { replays: [REPLAY, other] } });
    render(<Chat replay="other" />);
    expect(await screen.findByText('Other question')).toBeTruthy();
    expect(screen.queryByText('What was the 2025 LCR?')).toBeNull();
    cleanup();
    render(<Chat replay="missing" />);
    expect(await screen.findByText(/No recorded session with id/)).toBeTruthy();
  });

  it('shows the empty and error states', async () => {
    mockFetch({ '/v1/admin/config': CONFIG, '/v1/admin/replays': { replays: [] } });
    render(<Chat />);
    expect(await screen.findByText('No recorded sessions yet.')).toBeTruthy();
    cleanup();
    mockFetch({ '/v1/admin/config': CONFIG });
    render(<Chat />);
    expect((await screen.findByRole('alert')).textContent).toContain('no /v1/admin/replays');
  });
});
