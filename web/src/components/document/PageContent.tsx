// The tables and text of one page from /v1/read: each table's Markdown as an HTML table, then the page text.
import { api } from '../../api/client';
import { useAsync } from '../../lib/hooks';
import { ErrorBanner, Loading } from '../Shared';
import { parsePipeTable } from './pipeTable';

export function PipeTable({ markdown }: { markdown: string }) {
  const { header, rows } = parsePipeTable(markdown);
  if (!header && rows.length === 0) return <p className="muted">Empty table.</p>;
  return (
    <div className="pipe-table-wrap">
      <table className="grid pipe-table">
        {header && (
          <thead>
            <tr>{header.map((c, i) => <th key={i}>{c}</th>)}</tr>
          </thead>
        )}
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PageContent({ docId, page }: { docId: string; page: number }) {
  const read = useAsync(() => api.read({ doc_id: docId, page_range: [page, page] }), [docId, page]);
  if (read.loading) return <Loading what="page text" />;
  if (read.error) return <ErrorBanner error={read.error} />;
  const result = read.data?.results[0];
  if (!result) return <p className="muted">Nothing was read for this page.</p>;
  const tables = result.tables ?? [];
  return (
    <div className="page-content">
      <h3>Tables ({tables.length})</h3>
      {tables.length === 0 && <p className="muted">No tables on this page.</p>}
      {tables.map((t) => (
        <details key={t.table_id} open className="page-table">
          <summary className="mono">{t.table_id}</summary>
          {t.markdown ? <PipeTable markdown={t.markdown} /> : <p className="muted">No Markdown for this table.</p>}
        </details>
      ))}
      <details open className="page-text">
        <summary>Page text</summary>
        {result.text ? <pre>{result.text}</pre> : <p className="muted">No text on this page.</p>}
      </details>
    </div>
  );
}
