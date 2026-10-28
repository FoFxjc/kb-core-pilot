// Previous / next, a page number input, and the physical and printed page of the current page.
import { useEffect, useState, type FormEvent } from 'react';

export function PageNav({ page, pageCount, pageLabel, onGo }: {
  page: number;
  pageCount: number | null;
  pageLabel: string | null | undefined;
  onGo: (page: number) => void;
}) {
  const [value, setValue] = useState(String(page));
  useEffect(() => setValue(String(page)), [page]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const n = Number(value);
    if (!Number.isInteger(n)) return;
    onGo(Math.max(1, pageCount ? Math.min(n, pageCount) : n));
  };
  return (
    <form className="page-nav" onSubmit={submit}>
      <button type="button" onClick={() => onGo(page - 1)} disabled={page <= 1}>Previous</button>
      <label>
        Page{' '}
        <input type="number" min={1} max={pageCount ?? undefined} value={value} aria-label="Page number"
          onChange={(e) => setValue(e.target.value)} />
      </label>
      <button type="submit">Go</button>
      <button type="button" onClick={() => onGo(page + 1)} disabled={pageCount !== null && page >= pageCount}>Next</button>
      <span className="page-where">
        physical page {page}{pageCount ? ` of ${pageCount}` : ''} / printed page {pageLabel ?? 'n/a'}
      </span>
    </form>
  );
}
