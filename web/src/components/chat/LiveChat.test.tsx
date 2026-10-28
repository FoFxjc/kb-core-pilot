import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setPickerEnabled } from '../../lib/subject';
import { parseSse } from '../../api/client';
import { Chat } from '../../pages/Chat';

const STATUS = { contract: 'v1', enabled: true, reason: null, model: 'test-model', max_tool_calls: 8, busy: false,
  calls_used: 0, budget_calls: null };
const SID = 'chat_' + 'a'.repeat(32);

const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const STREAM = [
  sse('session', { session_id: SID, model: 'test-model', tool_calls_used: 0, max_tool_calls: 8 }),
  sse('thinking', { text: 'look up the series' }),
  sse('tool_call', { n: 1, tool: 'get_metric_series', input: { concept_id: 'npl_ratio' } }),
  sse('tool_result', { n: 1, tool: 'get_metric_series', status: 200, trace_id: 'tr_x', ms: 12, count: 2, gaps: [] }),
  sse('answer', { session_id: SID, answer: 'NPL ratio 0.9 (ocbc-group_ar_2025_en, physical page 98, printed page 96); ' +
    'made-up 4.2.', trace_id: 'tr_ans', model_calls: 2, tool_calls: 1, session_tool_calls: 1, usage: {},
    number_check: { checked: 2, skipped: 1, verified: [{ text: '0.9', context: 'NPL ratio 0.9' }],
      unverified: [{ text: '4.2', context: 'made-up 4.2.' }] }, error: null }),
];

function streamResponse(chunks: string[]): Response {
  const enc = new TextEncoder();
  return new Response(new ReadableStream({
    start(c) { chunks.forEach((x) => c.enqueue(enc.encode(x))); c.close(); },
  }), { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

function mockFetch(status: unknown, chat: () => Response) {
  const fn = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url === '/v1/admin/config') return new Response(JSON.stringify({ llm_enabled: false, live_chat: true, mode: 'live' }));
    if (url === '/v1/admin/chat/status') return new Response(JSON.stringify(status));
    if (url === '/v1/admin/chat') return chat();
    return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: url } }), { status: 404 });
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('parseSse', () => {
  it('returns complete events and keeps the unfinished rest', () => {
    // split in the middle of the second event
    const text = STREAM.slice(0, 2).join('');
    const cut = text.length - 10;
    const first = parseSse(text.slice(0, cut));
    expect(first.events.map((e) => e.event)).toEqual(['session']);
    const second = parseSse(first.rest + text.slice(cut));
    expect(second.events).toEqual([{ event: 'thinking', data: { text: 'look up the series' } }]);
    expect(second.rest).toBe('');
  });
});

describe('Live chat', () => {
  beforeEach(() => {
    setPickerEnabled(true);         // development: the dev role picker is on
    window.history.replaceState(null, '', '/ui/chat?mode=live');
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it('streams a turn: steps, answer with citation link, unverified numbers, session in the URL', async () => {
    const fetch = mockFetch(STATUS, () => streamResponse(STREAM));
    render(<Chat live />);
    const box = await screen.findByLabelText('Question');
    fireEvent.change(box, { target: { value: 'How did the NPL ratio change?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));

    expect(await screen.findByText(/1 of 2 numbers were not found/)).toBeTruthy();
    expect(screen.getByText('How did the NPL ratio change?')).toBeTruthy();
    expect(screen.getByText('get_metric_series')).toBeTruthy();
    expect(screen.getByText(/2 results · 12 ms/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'trace' }).getAttribute('href')).toBe('/ui/trace/tr_x');
    expect(screen.getByText('4.2')).toBeTruthy();
    const citation = screen.getAllByRole('link').find((a) => a.getAttribute('href')?.includes('/pages/98'));
    expect(citation).toBeTruthy();
    expect(window.location.search).toBe(`?mode=live&session=${SID}`);
    expect(screen.getByText('tool calls 1/8', { exact: false })).toBeTruthy();

    const body = JSON.parse(fetch.mock.calls.find((c) => c[0] === '/v1/admin/chat')![1]!.body as string);
    expect(body).toEqual({ message: 'How did the NPL ratio change?', subject: 'public' });
  });

  it('sends the session id on the next turn', async () => {
    const fetch = mockFetch(STATUS, () => streamResponse(STREAM));
    render(<Chat live session={SID} />);
    fireEvent.change(await screen.findByLabelText('Question'), { target: { value: 'and 2023?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    await screen.findByText(/numbers were not found/);
    const body = JSON.parse(fetch.mock.calls.find((c) => c[0] === '/v1/admin/chat')![1]!.body as string);
    expect(body).toEqual({ message: 'and 2023?', session_id: SID });
  });

  it('shows the server error and keeps the question when a turn is refused', async () => {
    mockFetch(STATUS, () => new Response(JSON.stringify({ error: { code: 'LAYER_UNAVAILABLE',
      message: 'another live chat is running' } }), { status: 409 }));
    render(<Chat live />);
    const box = await screen.findByLabelText('Question') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'q' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByText(/another live chat is running/)).toBeTruthy();
    expect((screen.getByLabelText('Question') as HTMLTextAreaElement).value).toBe('q');
  });

  it('reports a stream that ends without an answer instead of waiting forever', async () => {
    mockFetch(STATUS, () => streamResponse(STREAM.slice(0, 3)));
    render(<Chat live />);
    fireEvent.change(await screen.findByLabelText('Question'), { target: { value: 'q' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByText(/stream ended before the answer/)).toBeTruthy();
    expect(screen.queryByText(/Loading the agent/)).toBeNull();
  });

  it('explains why live chat is unavailable', async () => {
    mockFetch({ ...STATUS, enabled: false, reason: 'the model key is not set (KB_CORE_LLM_API_KEY)' },
      () => streamResponse([]));
    render(<Chat live />);
    expect(await screen.findByText(/the model key is not set/)).toBeTruthy();
    expect(screen.queryByLabelText('Question')).toBeNull();
  });
});
