import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { SUBJECT_KEY, resetSubject } from './lib/subject';

const STATUS = { enabled: true, reason: null, model: 'test-model', max_tool_calls: 8, busy: false, calls_used: 0,
  budget_calls: null };
const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const SID = 'chat_' + 'b'.repeat(32);
const STREAM = [
  sse('session', { session_id: SID, model: 'test-model', tool_calls_used: 0, max_tool_calls: 8 }),
  sse('answer', { session_id: SID, answer: 'An answer.', trace_id: 'tr_ans', model_calls: 1, tool_calls: 0,
    session_tool_calls: 0, usage: {}, number_check: null, error: null }),
];
const DOC = { doc_id: 'doc_a', issuer_id: 'x', doc_type: 'ar', fiscal_year: 2025, lang: 'en', page_count: 3,
  package: 'p', status: 'ok', primary_tree_source: null, tree_sample_accuracy: null };

function streamResponse(chunks: string[]): Response {
  const enc = new TextEncoder();
  return new Response(new ReadableStream({
    start(c) { chunks.forEach((x) => c.enqueue(enc.encode(x))); c.close(); },
  }), { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

function mockFetch(rolePicker = true) {
  const fn = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url === '/v1/admin/config') return new Response(JSON.stringify({ llm_enabled: false, live_chat: true, mode: 'live',
      role_picker: rolePicker }));
    if (url === '/v1/admin/chat/status') return new Response(JSON.stringify(STATUS));
    if (url === '/v1/admin/chat') return streamResponse(STREAM);
    if (url === '/v1/admin/docs') return new Response(JSON.stringify({ docs: [DOC] }));
    if (url === '/v1/admin/replays') return new Response(JSON.stringify({ replays: [] }));
    return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: url } }), { status: 404 });
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

const subjectOf = (init?: RequestInit) => new Headers(init?.headers).get('X-KB-Subject');
const picker = () => screen.getByLabelText('Viewing as') as HTMLSelectElement;

describe('dev role picker', () => {
  beforeEach(() => { window.localStorage.clear(); resetSubject(); window.history.replaceState(null, '', '/ui/docs'); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); window.localStorage.clear(); });

  it('defaults to public and sends it once the server allows the picker', async () => {
    const fetch = mockFetch();
    render(<App />);
    expect(await screen.findByLabelText('Viewing as')).toBeTruthy();
    expect(await screen.findByText('doc_a', { exact: false })).toBeTruthy();
    expect(picker().value).toBe('public');
    expect(screen.getByText('dev')).toBeTruthy();
    await waitFor(() => expect(subjectOf(fetch.mock.calls.filter((c) => c[0] === '/v1/admin/docs').at(-1)![1]))
      .toBe('public'));
  });

  it('is hidden behind the SSO gateway and never sends a subject', async () => {
    window.localStorage.setItem(SUBJECT_KEY, 'full_access');
    const fetch = mockFetch(false);
    render(<App />);
    expect(await screen.findByText('doc_a', { exact: false })).toBeTruthy();
    await waitFor(() => expect(fetch.mock.calls.some((c) => c[0] === '/v1/admin/config')).toBe(true));
    expect(screen.queryByLabelText('Viewing as')).toBeNull();
    for (const [, init] of fetch.mock.calls) expect(subjectOf(init)).toBeNull();
    const { api } = await import('./api/client');
    expect(api.pageImageUrl('doc_a', 2)).toBe('/v1/docs/doc_a/pages/2.png');
  });

  it('sends the chosen role, persists it and re-fetches the current view', async () => {
    const fetch = mockFetch();
    render(<App />);
    await screen.findByText('doc_a', { exact: false });
    const before = fetch.mock.calls.filter((c) => c[0] === '/v1/admin/docs').length;
    fireEvent.change(picker(), { target: { value: 'finance_analyst' } });
    await waitFor(() => expect(fetch.mock.calls.filter((c) => c[0] === '/v1/admin/docs').length).toBe(before + 1));
    const last = fetch.mock.calls.filter((c) => c[0] === '/v1/admin/docs').at(-1)!;
    expect(subjectOf(last[1])).toBe('finance_analyst');
    expect(window.localStorage.getItem(SUBJECT_KEY)).toBe('finance_analyst');
    cleanup();
    render(<App />);
    expect(picker().value).toBe('finance_analyst');
  });

  it('falls back to public when localStorage fails', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied'); });
    const fetch = mockFetch();
    render(<App />);
    await screen.findByText('doc_a', { exact: false });
    expect(picker().value).toBe('public');
    fireEvent.change(picker(), { target: { value: 'full_access' } });
    expect(picker().value).toBe('full_access');
    await waitFor(() => expect(subjectOf(fetch.mock.calls.at(-1)![1])).toBe('full_access'));
  });

  it('ignores an unknown stored role', async () => {
    window.localStorage.setItem(SUBJECT_KEY, 'root');
    mockFetch();
    render(<App />);
    await screen.findByLabelText('Viewing as');
    expect(picker().value).toBe('public');
  });

  it('starts a new chat session when the role changes', async () => {
    window.history.replaceState(null, '', '/ui/chat?mode=live');
    const fetch = mockFetch();
    render(<App />);
    fireEvent.change(await screen.findByLabelText('Question'), { target: { value: 'first' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByText('An answer.')).toBeTruthy();
    const chats = () => fetch.mock.calls.filter((c) => c[0] === '/v1/admin/chat');
    const first = chats()[0][1]!;
    expect(JSON.parse(first.body as string)).toEqual({ message: 'first', subject: 'public' });
    expect(subjectOf(first)).toBe('public');
    expect(window.location.search).toBe(`?mode=live&session=${SID}`);

    fireEvent.change(picker(), { target: { value: 'finance_confidential' } });
    expect(await screen.findByText(/new session/)).toBeTruthy();
    expect(screen.queryByText('first')).toBeNull();
    expect(window.location.search).toBe('?mode=live');

    fireEvent.change(await screen.findByLabelText('Question'), { target: { value: 'second' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    await waitFor(() => expect(chats()).toHaveLength(2));
    const second = chats()[1][1]!;
    expect(JSON.parse(second.body as string)).toEqual({ message: 'second', subject: 'finance_confidential' });
    expect(subjectOf(second)).toBe('finance_confidential');
  });
});
