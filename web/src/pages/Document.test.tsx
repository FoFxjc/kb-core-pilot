import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setPickerEnabled } from '../lib/subject';
import { DocumentView } from './Document';

const DOCS = {
  docs: [
    { doc_id: 'd_en', issuer_id: 'i', doc_type: 'annual_report', fiscal_year: 2025, lang: 'en', page_count: 10,
      package: 'p', status: 'built', primary_tree_source: 'regions',
      tree_sample_accuracy: { value: 0.825, correct: 33, sampled: 40 } },
    { doc_id: 'd_zh', issuer_id: 'i', doc_type: 'annual_report', fiscal_year: 2025, lang: 'zh', page_count: 8,
      package: 'p', status: 'built', primary_tree_source: 'outline', tree_sample_accuracy: null },
  ],
};

const n = (node_id: string, parent_id: string | null, depth: number, start_page: number, end_page: number,
  concepts: string[] = []) => ({
  node_id, parent_id, depth, title: `Title ${node_id}`, start_page, end_page,
  page_label_range: [String(start_page - 2), String(end_page - 2)], section_type: null,
  concepts: concepts.map((concept_id) => ({ concept_id })),
});

const NODES = {
  doc_id: 'd_en',
  tree_source: 'regions',
  nodes: [n('fin', null, 1, 1, 10), n('mda', 'fin', 2, 1, 5, ['net_profit']), n('ov', 'mda', 3, 3, 4), n('notes', 'fin', 2, 6, 10)],
};

const region = (id: string, type: string, bbox: [number, number, number, number], text: string) => ({
  region_id: id, type, subtype: null, layer: 'body', reading_order: Number(id.slice(1)), bbox, text, table_id: null,
  node_id: 'ov',
});

const REGIONS = {
  doc_id: 'd_en', page_no: 3, page_label: '1', width: 200, height: 400,
  regions: [
    region('r1', 'heading', [10, 10, 190, 30], 'Overview'),
    region('r2', 'text', [10, 40, 190, 80], 'First paragraph'),
    region('r3', 'text', [10, 90, 190, 120], 'Second paragraph'),
    region('r4', 'table', [10, 130, 190, 300], ''),
  ],
};

const READ = {
  contract: 'v1', tool: 'read', scope: {}, gaps: [], truncated: false, next: null, trace_id: 't',
  results: [{ tier: 'text', page_no: 3, page_label: '1', text: 'Overview\nFirst paragraph',
    tables: [{ table_id: 'd_en:p0003:t01', markdown: '|Item|2025|\n|---|---|\n|Net profit|7,422|' }] }],
};

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function mockFetch() {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === '/v1/admin/docs') return json(DOCS);
    if (url === '/v1/admin/docs/d_en/nodes') return json(NODES);
    if (url === '/v1/admin/docs/nope/nodes')
      return json({ contract: 'v1', error: { code: 'UNKNOWN_DOC', message: 'unknown doc_id: nope' } }, 404);
    if (url.startsWith('/v1/docs/d_en/pages/') && url.endsWith('/regions')) return json(REGIONS);
    if (url.startsWith('/v1/read?')) return json(READ);
    return json({ error: { code: 'NOT_FOUND', message: `unexpected ${url}` } }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  setPickerEnabled(true);           // development: the dev role picker is on
  mockFetch();
  window.history.replaceState(null, '', '/ui/docs');
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('DocumentView picker', () => {
  it('lists documents with their tree accuracy and links to page 1', async () => {
    render(<DocumentView />);
    const link = await screen.findByRole('link', { name: 'd_en' });
    expect(link.getAttribute('href')).toBe('/ui/docs/d_en/pages/1');
    expect(screen.getByText('82.5% (33/40)')).toBeTruthy();
    expect(screen.getByText('not checked')).toBeTruthy();
    expect(screen.getByText('outline')).toBeTruthy();
  });
});

describe('DocumentView page', () => {
  it('renders the tree, the page image, region boxes and the page tables', async () => {
    const { container } = render(<DocumentView docId="d_en" page={3} />);
    await screen.findByRole('link', { name: 'Title ov' });

    // Tree: nested, covering nodes highlighted, deepest marked, concept chip shown; "notes" does not cover page 3.
    const covering = [...container.querySelectorAll('[data-covering]')].map((e) => e.getAttribute('data-node-id'));
    expect(covering).toEqual(['fin', 'mda', 'ov']);
    expect(container.querySelector('.outline-row.deepest')?.getAttribute('data-node-id')).toBe('ov');
    expect(screen.getByText('net_profit')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Title notes' }).getAttribute('href')).toBe('/ui/docs/d_en/pages/6');

    // Page image and boxes in percent of the page size.
    const img = await screen.findByRole('img', { name: 'Page image' });
    expect(img.getAttribute('src')).toBe('/v1/docs/d_en/pages/3.png?subject=public');
    const boxes = () => [...container.querySelectorAll<HTMLElement>('.region-box')];
    expect(boxes().map((b) => b.dataset.regionType)).toEqual(['heading', 'text', 'text', 'table']);
    expect(boxes()[0].style.left).toBe('5%');
    expect(boxes()[0].style.top).toBe('2.5%');
    expect(boxes()[0].style.width).toBe('90%');
    expect(screen.getByText(/physical page 3 of 10 \/ printed page 1/)).toBeTruthy();

    // Toggling a type hides only its boxes.
    fireEvent.click(screen.getByRole('checkbox', { name: /text/ }));
    expect(boxes().map((b) => b.dataset.regionType)).toEqual(['heading', 'table']);
    fireEvent.click(screen.getByRole('checkbox', { name: /text/ }));
    expect(boxes()).toHaveLength(4);

    // Hover shows type, reading order and text.
    fireEvent.mouseEnter(boxes()[1]);
    expect(screen.getByRole('tooltip').textContent).toContain('reading order 2');
    expect(screen.getByRole('tooltip').textContent).toContain('First paragraph');

    // Right panel: the table as HTML and the page text.
    expect(await screen.findByRole('cell', { name: 'Net profit' })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: '2025' })).toBeTruthy();
    expect(screen.getByText(/First paragraph/, { selector: 'pre' })).toBeTruthy();
  });

  it('navigates with next and previous through the URL', async () => {
    render(<DocumentView docId="d_en" page={3} />);
    await screen.findByRole('img', { name: 'Page image' });
    act(() => fireEvent.click(screen.getByRole('button', { name: 'Next' })));
    expect(window.location.pathname).toBe('/ui/docs/d_en/pages/4');
    act(() => fireEvent.click(screen.getByRole('button', { name: 'Previous' })));
    expect(window.location.pathname).toBe('/ui/docs/d_en/pages/2');
  });

  it('shows an out-of-range page without fetching it', async () => {
    const fetchMock = mockFetch();
    render(<DocumentView docId="d_en" page={99} />);
    expect(await screen.findByText(/Page 99 is out of range: this document has pages 1 to 10/)).toBeTruthy();
    expect(fetchMock.mock.calls.map((c) => String(c[0])).some((u) => u.includes('/pages/99'))).toBe(false);
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('shows the API error for an unknown document', async () => {
    render(<DocumentView docId="nope" page={1} />);
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('unknown doc_id: nope'));
  });
});
