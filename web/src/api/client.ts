// Typed client for the kb-core HTTP API (docs/api-contract.md). Paths come from the generated OpenAPI schema;
// the routes return plain JSON objects, so their shapes are written out here from the contract (sections 4, 5, 8).
import { sentSubject } from '../lib/subject';
import type { paths } from './schema.gen';

export type ApiPath = keyof paths;

export type Tier = 'fact' | 'link' | 'structure' | 'text';
export type Severity = 'info' | 'warn';

export interface Source {
  doc_id: string;
  lang?: string;
  fiscal_year?: number;
  node_id?: string;
  title_path?: string[];
  page_range: [number, number] | null;
  page_label_range?: [string | null, string | null] | null;
  table_id?: string | null;
  row_label?: string | null;
  snippet?: string | null;
}

export interface Gap {
  code: string;
  severity?: Severity;
  detail?: string;
  doc_id?: string;
  next?: { tool: string; params: Record<string, unknown>; why?: string }[];
  [key: string]: unknown;
}

export interface Result {
  tier: Tier;
  status?: string;
  rank: number;
  score?: number | null;
  node_id?: string | null;
  title?: string;
  section_type?: string | null;
  snippet?: string | null;
  source?: Source;
  sources?: Source[];
  [key: string]: unknown;
}

export interface Envelope {
  contract: string;
  tool: string;
  results: Result[];
  scope: Record<string, unknown>;
  gaps: Gap[];
  truncated: boolean;
  next: unknown;
  trace_id: string;
}

export interface TraceSummary {
  trace_id: string;
  tool: string;
  source: string;
  session_id: string | null;
  started_at: string;
  duration_ms: number;
  status: 'ok' | 'error';
  error: string | null;
  input: Record<string, unknown>;
  gaps: Gap[] | null;
  n_results: number;
}

/** One traced call. `output.detail` holds per-route ranks (`routes`), coverage drops (`coverage_dropped`),
 * layer decisions (`tier_decisions`) and the final DSL/SQL per template id (`queries`). */
export interface Trace {
  trace_id: string;
  tool: string;
  source: string;
  session_id: string | null;
  started_at: string;
  duration_ms: number;
  status: 'ok' | 'error';
  error: string | null;
  input: Record<string, unknown>;
  output: {
    results?: Record<string, unknown>[];
    scope?: Record<string, unknown>;
    gaps?: Gap[];
    truncated?: boolean;
    detail?: TraceDetail;
    error?: unknown;
  };
}

export interface TraceDetail {
  routes?: Record<string, Record<string, string[]>>;
  queries?: Record<string, unknown>;
  coverage_dropped?: Record<string, Record<string, [string, number][]>>;
  tier_decisions?: Record<string, { tier: Tier; title_terms?: string[]; coverage?: Record<string, number>; concepts?: unknown[] }>;
  coverage_threshold?: number;
  [key: string]: unknown;
}

export interface Replay {
  id: string;
  run: string | null;
  session_id: string | null;
  questions: Record<string, string>;
  answer: string | null;
  tool_calls: { tool: string; trace_id: string; params: Record<string, unknown> }[];
}

export interface DocSummary {
  doc_id: string;
  issuer_id: string;
  doc_type: string;
  fiscal_year: number;
  lang: string | null;
  page_count: number;
  package: string;
  status: string;
  primary_tree_source: string | null;
  tree_sample_accuracy: { value: number; correct: number; sampled: number } | null;
}

export interface TreeNode {
  node_id: string;
  parent_id: string | null;
  depth: number;
  title: string;
  start_page: number;
  end_page: number;
  page_label_range: [string | null, string | null] | null;
  section_type: string | null;
  concepts: { concept_id: string; method?: string; confidence?: number }[];
}

export interface Region {
  region_id: string;
  type: string;
  subtype: string | null;
  layer: string;
  reading_order: number;
  bbox: [number, number, number, number];
  text: string | null;
  table_id: string | null;
  node_id: string | null;
}

export interface ReadPage {
  page_no: number;
  page_label: string | null;
  text: string;
  tables?: { table_id: string; markdown?: string; bbox?: number[] }[];
  [key: string]: unknown;
}

export interface ChatStatus {
  enabled: boolean;
  reason: string | null;
  model: string | null;
  max_tool_calls: number;
  busy: boolean;
  calls_used: number;
  budget_calls: number | null;
}

export interface NumberCheck {
  checked: number;
  verified: { text: string; context: string }[];
  unverified: { text: string; context: string }[];
  skipped: number;
}

/** Server-sent events of POST /v1/admin/chat (api-contract section 8). */
export type ChatEvent =
  | { event: 'session'; data: { session_id: string; model: string; tool_calls_used: number; max_tool_calls: number } }
  | { event: 'thinking'; data: { text: string } }
  | { event: 'text'; data: { text: string } }
  | { event: 'tool_call'; data: { n: number; tool: string; input: Record<string, unknown> } }
  | { event: 'tool_result'; data: { n?: number; tool: string; status?: number; trace_id?: string | null; ms?: number;
      count?: number; gaps?: string[]; error?: string; skipped?: boolean; reason?: string; [key: string]: unknown } }
  | { event: 'error'; data: { message: string; trace_id: string; session_id: string } }
  | { event: 'answer'; data: { session_id: string; answer: string; trace_id: string; model_calls: number;
      tool_calls: number; session_tool_calls: number; usage: Record<string, number>;
      number_check: NumberCheck | null; error: string | null } };

/** Split a server-sent-event text buffer into complete events and the unfinished rest. */
export function parseSse(buffer: string): { events: ChatEvent[]; rest: string } {
  const blocks = buffer.replace(/\r\n/g, '\n').split('\n\n');
  const rest = blocks.pop() ?? '';
  const events: ChatEvent[] = [];
  for (const block of blocks) {
    let event = 'message';
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
    }
    if (data.length) events.push({ event, data: JSON.parse(data.join('\n')) } as ChatEvent);
  }
  return { events, rest };
}

/** One live chat turn: streams events to `onEvent` until the answer; validation errors throw ApiError. A new session
 * names its subject in the body; an existing session keeps the subject it started with (the server refuses another). */
export async function chatTurn(message: string, sessionId: string | null, onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal): Promise<void> {
  const res = await fetch('/v1/admin/chat', {
    method: 'POST', signal,
    headers: { ...baseHeaders(), 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(sessionId ? { message, session_id: sessionId }
      : sentSubject() ? { message, subject: sentSubject() } : { message }),
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null);
    const err = body?.error ?? {};
    throw new ApiError(res.status, err.code ?? 'HTTP', err.message ?? `${res.status} ${res.statusText}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let answered = false;
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const parsed = parseSse(done ? buffer + '\n\n' : buffer);
    buffer = parsed.rest;
    for (const ev of parsed.events) {
      if (ev.event === 'answer') answered = true;
      onEvent(ev);
    }
    if (done) {
      if (!answered) throw new ApiError(502, 'STREAM_ENDED', 'the answer stream ended before the answer');
      return;
    }
  }
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

/** Headers on every API request: the caller (ui) and, while the dev role picker is on, the chosen subject. Page
 * images loaded through <img src> cannot carry headers, so their URLs name the subject in the query (pageImageUrl).
 * Behind the SSO gateway no subject is sent: the gateway's identity headers decide. */
const baseHeaders = (): Record<string, string> => {
  const subject = sentSubject();
  return subject ? { 'X-KB-Source': 'ui', 'X-KB-Subject': subject } : { 'X-KB-Source': 'ui' };
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { ...baseHeaders(), ...(init?.headers ?? {}) } });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = body?.error ?? {};
    throw new ApiError(res.status, err.code ?? 'HTTP', err.message ?? `${res.status} ${res.statusText}`);
  }
  return body as T;
}

const q = (params: Record<string, string | number | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') s.set(k, String(v));
  const out = s.toString();
  return out ? `?${out}` : '';
};

const post = <T>(path: ApiPath, body: unknown) =>
  call<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

export const api = {
  config: () => call<{ llm_enabled: boolean; live_chat: boolean; mode: 'replay' | 'live'; role_picker?: boolean }>(
    '/v1/admin/config'),
  replays: () => call<{ replays: Replay[] }>('/v1/admin/replays'),
  chatStatus: () => call<ChatStatus>('/v1/admin/chat/status'),
  session: (id: string) => call<{ session_id: string; calls: (TraceSummary & { results?: unknown[] })[] }>(
    `/v1/admin/sessions/${encodeURIComponent(id)}`),
  traces: (p: { tool?: string; source?: string; session_id?: string; limit?: number; cursor?: string } = {}) =>
    call<{ traces: TraceSummary[]; next_cursor: string | null }>(`/v1/admin/traces${q(p)}`),
  trace: (id: string) => call<Trace>(`/v1/admin/traces/${encodeURIComponent(id)}`),
  docs: () => call<{ docs: DocSummary[] }>('/v1/admin/docs'),
  nodes: (docId: string) => call<{ doc_id: string; tree_source: string; nodes: TreeNode[] }>(
    `/v1/admin/docs/${encodeURIComponent(docId)}/nodes`),
  /** Regions of a page; bbox is in PDF points (origin top left) on a page of width x height points. */
  regions: (docId: string, page: number) => call<{ doc_id: string; page_no: number; page_label: string | null;
    width: number | null; height: number | null; regions: Region[] }>(
    `/v1/docs/${encodeURIComponent(docId)}/pages/${page}/regions`),
  // an <img> cannot send X-KB-Subject: the page image names the subject in the query instead
  pageImageUrl: (docId: string, page: number) => {
    const subject = sentSubject();
    return `/v1/docs/${encodeURIComponent(docId)}/pages/${page}.png`
      + (subject ? `?subject=${encodeURIComponent(subject)}` : '');
  },
  read: (p: { doc_id: string; page_range: [number, number]; include_tables?: boolean }) =>
    call<Envelope & { results: ReadPage[] }>(`/v1/read${q({ doc_id: p.doc_id,
      page_range: `${p.page_range[0]}-${p.page_range[1]}`, include_tables: p.include_tables === false ? 'false' : undefined })}`),
  search: (body: Record<string, unknown>) => post<Envelope>('/v1/search', body),
};
