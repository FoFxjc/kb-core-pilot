// View 3, document & evidence: without a document a picker; with one the primary tree (left), the page image with
// region boxes (centre) and the page's tables and text (right). Deep link /ui/docs/:doc_id/pages/:n.
import { useState } from 'react';
import { api } from '../api/client';
import { DocPicker } from '../components/document/DocPicker';
import { OutlineTree } from '../components/document/OutlineTree';
import { PageContent } from '../components/document/PageContent';
import { PageImage } from '../components/document/PageImage';
import { PageNav } from '../components/document/PageNav';
import '../components/document/document.css';
import { ErrorBanner, Link, Loading } from '../components/Shared';
import { useAsync } from '../lib/hooks';
import { href, navigate } from '../lib/router';

export function DocumentView({ docId, page }: { docId?: string; page?: number }) {
  const docs = useAsync(() => api.docs(), []);
  if (!docId) {
    return (
      <section className="view doc-view" data-view="document">
        <h2>Documents</h2>
        {docs.loading && <Loading what="documents" />}
        <ErrorBanner error={docs.error} />
        {docs.data && <DocPicker docs={docs.data.docs} />}
      </section>
    );
  }
  const doc = docs.data?.docs.find((d) => d.doc_id === docId) ?? null;
  return (
    <section className="view doc-view" data-view="document">
      <ErrorBanner error={docs.error} />
      <DocumentPages docId={docId} page={page ?? 1} pageCount={doc?.page_count ?? null} docsLoaded={!!docs.data} />
    </section>
  );
}

function DocumentPages({ docId, page, pageCount, docsLoaded }: {
  docId: string; page: number; pageCount: number | null; docsLoaded: boolean;
}) {
  const nodes = useAsync(() => api.nodes(docId), [docId]);
  const inRange = pageCount !== null && page >= 1 && page <= pageCount;
  const regions = useAsync(() => (inRange ? api.regions(docId, page) : Promise.resolve(null)), [docId, page, inRange]);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(() => new Set());
  const go = (p: number) => navigate(href({ view: 'document', docId, page: p }));
  const toggleType = (t: string) =>
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });

  // An unknown document: the tree request answers 404 with the known doc_ids.
  if (nodes.error) {
    return (
      <>
        <ErrorBanner error={nodes.error} />
        <Link to={{ view: 'document' }}>Back to the document list</Link>
      </>
    );
  }

  return (
    <div className="doc-layout">
      <aside className="doc-tree panel">
        <div className="doc-tree-head">
          <Link to={{ view: 'document' }}>Documents</Link> / <span className="mono">{docId}</span>
          {nodes.data && <div className="muted">Tree source: {nodes.data.tree_source}</div>}
        </div>
        {nodes.loading && <Loading what="tree" />}
        {nodes.data && <OutlineTree key={docId} docId={docId} nodes={nodes.data.nodes} page={page} />}
      </aside>

      <div className="doc-page panel">
        <PageNav page={page} pageCount={pageCount} pageLabel={regions.data?.page_label} onGo={go} />
        {!docsLoaded && <Loading what="document" />}
        {docsLoaded && !inRange && (
          <div className="error-banner" role="alert">
            {pageCount === null
              ? `Unknown document: ${docId}.`
              : `Page ${page} is out of range: this document has pages 1 to ${pageCount}.`}
            {pageCount !== null && (
              <> <Link to={{ view: 'document', docId, page: 1 }}>Go to page 1</Link></>
            )}
          </div>
        )}
        {inRange && regions.loading && <Loading what="regions" />}
        <ErrorBanner error={regions.error} />
        {inRange && regions.data && (
          <PageImage src={api.pageImageUrl(docId, page)} regions={regions.data.regions} width={regions.data.width}
            height={regions.data.height} hidden={hiddenTypes} onToggleType={toggleType} />
        )}
      </div>

      <aside className="doc-content panel">
        {inRange ? <PageContent docId={docId} page={page} /> : <p className="muted">No page selected.</p>}
      </aside>
    </div>
  );
}
