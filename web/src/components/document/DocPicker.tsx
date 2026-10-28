// The document list: one row per imported document, each linking to its first page.
import type { DocSummary } from '../../api/client';
import { Link } from '../Shared';

export function accuracyText(a: DocSummary['tree_sample_accuracy']): string {
  if (!a) return 'not checked';
  return `${Number((a.value * 100).toFixed(1))}% (${a.correct}/${a.sampled})`;
}

export function DocPicker({ docs }: { docs: DocSummary[] }) {
  if (docs.length === 0) return <p className="muted">No documents have been imported.</p>;
  return (
    <table className="grid doc-picker">
      <thead>
        <tr>
          <th>Document</th>
          <th>Language</th>
          <th>Fiscal year</th>
          <th>Pages</th>
          <th>Tree source</th>
          <th>Tree spot-check accuracy</th>
        </tr>
      </thead>
      <tbody>
        {docs.map((d) => (
          <tr key={d.doc_id} data-doc-id={d.doc_id}>
            <td>
              <Link to={{ view: 'document', docId: d.doc_id, page: 1 }} className="mono">{d.doc_id}</Link>
            </td>
            <td>{d.lang ?? 'n/a'}</td>
            <td>{d.fiscal_year}</td>
            <td>{d.page_count}</td>
            <td>{d.primary_tree_source ?? 'n/a'}</td>
            <td>{accuracyText(d.tree_sample_accuracy)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
