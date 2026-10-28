// A small, safe Markdown subset for recorded agent answers: paragraphs, headings, **bold**, "-" lists, "|" tables and
// "---" rules. Everything renders as React elements (no HTML injection). Citations in the contract form
// "(doc_id, physical page N, printed page M)" become links to the document view at page N.
import { Fragment, type ReactNode } from 'react';
import type { Source } from '../../api/client';
import { Citation } from '../Shared';

export type CitationSource = Pick<Source, 'doc_id' | 'page_range' | 'page_label_range'>;
export type InlinePart = { kind: 'text'; text: string } | { kind: 'citation'; source: CitationSource; raw: string };

// doc ids look like "ocbc-group_ar_2025_en": anything ending in _<year>_<lang>, plus any "ocbc..." id.
const CITATION =
  /\((ocbc[^,()]+|[A-Za-z0-9][A-Za-z0-9_.-]*_\d{4}_[a-z]{2}), physical page (\d+)(?:-(\d+))?, printed page ([^)]+)\)/g;

function printedRange(label: string): [string | null, string | null] | null {
  const t = label.trim();
  if (!t || t === 'n/a') return null;
  const m = /^([^-\s]+)\s*-\s*([^-\s]+)$/.exec(t);
  return m ? [m[1], m[2]] : [t, t];
}

/** Split text into plain runs and contract citations. */
export function parseCitations(text: string): InlinePart[] {
  const parts: InlinePart[] = [];
  let last = 0;
  for (const m of text.matchAll(CITATION)) {
    const at = m.index ?? 0;
    if (at > last) parts.push({ kind: 'text', text: text.slice(last, at) });
    const start = Number(m[2]);
    const end = m[3] ? Number(m[3]) : start;
    parts.push({ kind: 'citation', raw: m[0],
      source: { doc_id: m[1].trim(), page_range: [start, end], page_label_range: printedRange(m[4]) } });
    last = at + m[0].length;
  }
  if (last < text.length) parts.push({ kind: 'text', text: text.slice(last) });
  return parts;
}

export type Block =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'list'; items: string[] }
  | { kind: 'table'; header: string[]; rows: string[][] }
  | { kind: 'rule' };

const splitRow = (line: string) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
const isSeparatorRow = (line: string) => /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/.test(line.trim());

/** Group lines into blocks; unknown syntax falls through as paragraph text. */
export function parseBlocks(md: string): Block[] {
  const lines = md.replace(/\r\n?/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) { i++; continue; }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2] });
      i++;
    } else if (/^-{3,}$/.test(line) || /^\*{3,}$/.test(line)) {
      blocks.push({ kind: 'rule' });
      i++;
    } else if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) items.push(lines[i++].trim().replace(/^[-*]\s+/, ''));
      blocks.push({ kind: 'list', items });
    } else if (line.startsWith('|')) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++].trim());
      const hasHeader = rows.length > 1 && isSeparatorRow(rows[1]);
      const body = (hasHeader ? rows.slice(2) : rows).filter((r) => !isSeparatorRow(r)).map(splitRow);
      blocks.push({ kind: 'table', header: hasHeader ? splitRow(rows[0]) : [], rows: body });
    } else {
      const para: string[] = [];
      while (i < lines.length) {
        const l = lines[i].trim();
        if (!l || /^(#{1,6})\s+/.test(l) || /^-{3,}$/.test(l) || /^[-*]\s+/.test(l) || l.startsWith('|')) break;
        para.push(l);
        i++;
      }
      blocks.push({ kind: 'paragraph', text: para.join('\n') });
    }
  }
  return blocks;
}

function withCitations(text: string): ReactNode[] {
  return parseCitations(text).map((p, k) =>
    p.kind === 'text' ? <Fragment key={k}>{p.text}</Fragment> : <Citation key={k} source={p.source} />);
}

/** Inline text: **bold** runs and citations; line breaks inside a paragraph are kept. */
export function Inline({ text }: { text: string }) {
  const out: ReactNode[] = [];
  text.split('\n').forEach((line, li) => {
    if (li > 0) out.push(<br key={`br${li}`} />);
    line.split(/\*\*(.+?)\*\*/g).forEach((seg, si) => {
      if (!seg) return;
      const kids = withCitations(seg);
      out.push(si % 2 === 1 ? <strong key={`${li}-${si}`}>{kids}</strong> : <Fragment key={`${li}-${si}`}>{kids}</Fragment>);
    });
  });
  return <>{out}</>;
}

function Heading({ level, text }: { level: number; text: string }) {
  const content = <Inline text={text} />;
  // The page owns h1/h2; answer headings start at h3.
  if (level <= 3) return <h3>{content}</h3>;
  if (level === 4) return <h4>{content}</h4>;
  return <h5>{content}</h5>;
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      {parseBlocks(text).map((b, k) => {
        switch (b.kind) {
          case 'heading':
            return <Heading key={k} level={b.level} text={b.text} />;
          case 'rule':
            return <hr key={k} />;
          case 'list':
            return (
              <ul key={k}>
                {b.items.map((it, j) => <li key={j}><Inline text={it} /></li>)}
              </ul>
            );
          case 'table':
            return (
              <table key={k} className="grid md-table">
                {b.header.length > 0 && (
                  <thead>
                    <tr>{b.header.map((c, j) => <th key={j}><Inline text={c} /></th>)}</tr>
                  </thead>
                )}
                <tbody>
                  {b.rows.map((r, j) => (
                    <tr key={j}>{r.map((c, n) => <td key={n}><Inline text={c} /></td>)}</tr>
                  ))}
                </tbody>
              </table>
            );
          default:
            return <p key={k}><Inline text={b.text} /></p>;
        }
      })}
    </div>
  );
}
