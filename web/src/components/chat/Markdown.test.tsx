import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Markdown, parseBlocks, parseCitations } from './Markdown';

describe('parseCitations', () => {
  it('finds the contract form and keeps the text around it', () => {
    const parts = parseCitations('NPL 0.9 (ocbc-group_ar_2025_en, physical page 98, printed page 96) end');
    expect(parts).toEqual([
      { kind: 'text', text: 'NPL 0.9 ' },
      { kind: 'citation', raw: '(ocbc-group_ar_2025_en, physical page 98, printed page 96)',
        source: { doc_id: 'ocbc-group_ar_2025_en', page_range: [98, 98], page_label_range: ['96', '96'] } },
      { kind: 'text', text: ' end' },
    ]);
  });

  it('reads page ranges, n/a printed pages and other doc ids', () => {
    const [a, , b] = parseCitations('(ocbc-group_ar_2024_en, physical page 98-100, printed page 96-98) and ' +
      '(acme_ar_2023_zh, physical page 4, printed page n/a)');
    expect(a).toMatchObject({ kind: 'citation',
      source: { doc_id: 'ocbc-group_ar_2024_en', page_range: [98, 100], page_label_range: ['96', '98'] } });
    expect(b).toMatchObject({ kind: 'citation',
      source: { doc_id: 'acme_ar_2023_zh', page_range: [4, 4], page_label_range: null } });
  });

  it('leaves text without a citation alone', () => {
    const plain = 'page 98 of the 2024 report (printed page 96) was not read (see above)';
    expect(parseCitations(plain)).toEqual([{ kind: 'text', text: plain }]);
    expect(parseCitations('')).toEqual([]);
  });
});

describe('Markdown subset', () => {
  const md = ['intro line', '', '---', '', '### 1. Title', '', '**bold** start', '', '- one', '- two **b**', '',
    '| Year | Value |', '|---|---|', '| 2024 | **7,587** |', '| 2025 | 7,422 |'].join('\n');

  it('groups lines into blocks', () => {
    expect(parseBlocks(md)).toEqual([
      { kind: 'paragraph', text: 'intro line' },
      { kind: 'rule' },
      { kind: 'heading', level: 3, text: '1. Title' },
      { kind: 'paragraph', text: '**bold** start' },
      { kind: 'list', items: ['one', 'two **b**'] },
      { kind: 'table', header: ['Year', 'Value'], rows: [['2024', '**7,587**'], ['2025', '7,422']] },
    ]);
  });

  it('renders elements, never raw HTML', () => {
    const { container } = render(<Markdown text={md + '\n\n<img src=x onerror=alert(1)> (d_2025_en, physical page 5, printed page 3)'} />);
    expect(screen.getByRole('heading', { level: 3 }).textContent).toBe('1. Title');
    expect(container.querySelector('hr')).not.toBeNull();
    expect(container.querySelectorAll('li')).toHaveLength(2);
    expect(container.querySelectorAll('strong')).toHaveLength(3);
    expect(container.querySelectorAll('th')).toHaveLength(2);
    expect(container.querySelectorAll('tbody tr')).toHaveLength(2);
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(screen.getByRole('link').getAttribute('href')).toBe('/ui/docs/d_2025_en/pages/5');
  });
});
