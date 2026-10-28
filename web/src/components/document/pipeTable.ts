// A small Markdown pipe-table parser: header row, optional separator row, body rows. Cells are plain text.
export interface PipeTableData {
  header: string[] | null;
  rows: string[][];
}

const SEPARATOR = /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$/;

/** Split one row on unescaped pipes, dropping the outer pipes; "\|" stays a literal pipe. */
export function splitRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1);
  const cells: string[] = [];
  let cur = '';
  for (let i = 0; i < s.length; i++) {
    if (s[i] === '\\' && s[i + 1] === '|') {
      cur += '|';
      i++;
    } else if (s[i] === '|') {
      cells.push(cur.trim());
      cur = '';
    } else cur += s[i];
  }
  cells.push(cur.trim());
  return cells;
}

export function parsePipeTable(markdown: string): PipeTableData {
  const lines = markdown.split('\n').map((l) => l.trim()).filter((l) => l.startsWith('|'));
  if (lines.length === 0) return { header: null, rows: [] };
  const hasHeader = lines.length > 1 && SEPARATOR.test(lines[1]);
  const header = hasHeader ? splitRow(lines[0]) : null;
  const body = (hasHeader ? lines.slice(2) : lines).map(splitRow);
  const width = Math.max(header?.length ?? 0, ...body.map((r) => r.length));
  const pad = (r: string[]) => (r.length < width ? [...r, ...Array(width - r.length).fill('')] : r);
  return { header: header ? pad(header) : null, rows: body.map(pad) };
}
