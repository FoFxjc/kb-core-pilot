// The primary tree as a collapsible outline. Nodes covering the current page are highlighted, the deepest one is
// kept scrolled into view, and a click on a title opens the node's start page.
import { useEffect, useMemo, useRef, useState } from 'react';
import type { TreeNode } from '../../api/client';
import { Link } from '../Shared';
import { buildTree, covers, deepestCovering, expandedFor, type OutlineNode } from './tree';

function rangeText(a: string | number | null | undefined, b: string | number | null | undefined): string {
  if (a === null || a === undefined) return 'n/a';
  return a === b || b === null || b === undefined ? `${a}` : `${a}-${b}`;
}

export function OutlineTree({ docId, nodes, page }: { docId: string; nodes: TreeNode[]; page: number }) {
  const roots = useMemo(() => buildTree(nodes), [nodes]);
  const deepest = useMemo(() => deepestCovering(nodes, page), [nodes, page]);
  const [expanded, setExpanded] = useState<Set<string>>(() => expandedFor(nodes, page));
  const deepestRef = useRef<HTMLDivElement | null>(null);

  // A new page opens the path to every node covering it; nodes the reader opened stay open.
  useEffect(() => {
    setExpanded((prev) => new Set([...prev, ...expandedFor(nodes, page)]));
  }, [nodes, page]);

  useEffect(() => {
    deepestRef.current?.scrollIntoView?.({ block: 'nearest' });
  }, [deepest, expanded]);

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const renderNode = (n: OutlineNode) => {
    const open = expanded.has(n.node_id);
    const current = covers(n, page);
    const isDeepest = deepest?.node_id === n.node_id;
    return (
      <li key={n.node_id}>
        <div
          className={`outline-row${current ? ' covering' : ''}${isDeepest ? ' deepest' : ''}`}
          data-node-id={n.node_id}
          data-covering={current || undefined}
          ref={isDeepest ? deepestRef : undefined}
        >
          {n.children.length > 0 ? (
            <button type="button" className="outline-toggle" aria-expanded={open}
              aria-label={`${open ? 'Collapse' : 'Expand'} ${n.title}`} onClick={() => toggle(n.node_id)}>
              {open ? '▾' : '▸'}
            </button>
          ) : (
            <span className="outline-toggle" />
          )}
          <div className="outline-body">
            <Link to={{ view: 'document', docId, page: n.start_page }} className="outline-title">{n.title}</Link>
            <div className="outline-meta muted">
              p. {rangeText(n.start_page, n.end_page)} · printed {rangeText(n.page_label_range?.[0], n.page_label_range?.[1])}
            </div>
            {n.concepts.length > 0 && (
              <div className="chips">
                {n.concepts.map((c) => (
                  <span key={c.concept_id} className="chip mono" title={c.method}>{c.concept_id}</span>
                ))}
              </div>
            )}
          </div>
        </div>
        {open && n.children.length > 0 && <ul>{n.children.map(renderNode)}</ul>}
      </li>
    );
  };

  if (nodes.length === 0) return <p className="muted">This document has no primary tree.</p>;
  return <ul className="outline" aria-label="Primary tree">{roots.map(renderNode)}</ul>;
}
