// Primary-tree helpers: nest the flat node list by parent_id and find the nodes covering a page.
import type { TreeNode } from '../../api/client';

export interface OutlineNode extends TreeNode {
  children: OutlineNode[];
}

/** Nest flat nodes by parent_id, keeping the input order among siblings. A node whose parent is missing becomes a root. */
export function buildTree(nodes: TreeNode[]): OutlineNode[] {
  const byId = new Map<string, OutlineNode>();
  for (const n of nodes) byId.set(n.node_id, { ...n, children: [] });
  const roots: OutlineNode[] = [];
  for (const n of nodes) {
    const node = byId.get(n.node_id)!;
    const parent = n.parent_id ? byId.get(n.parent_id) : undefined;
    if (parent && parent !== node) parent.children.push(node);
    else roots.push(node);
  }
  return roots;
}

export const covers = (n: Pick<TreeNode, 'start_page' | 'end_page'>, page: number) =>
  n.start_page <= page && page <= n.end_page;

/** Nodes whose physical page range contains the page, shallowest first. */
export function coveringNodes(nodes: TreeNode[], page: number): TreeNode[] {
  return nodes.filter((n) => covers(n, page)).sort((a, b) => a.depth - b.depth);
}

/** The deepest covering node; on a tie the one with the narrowest range, then the last in document order. */
export function deepestCovering(nodes: TreeNode[], page: number): TreeNode | null {
  let best: TreeNode | null = null;
  for (const n of nodes) {
    if (!covers(n, page)) continue;
    if (!best || n.depth > best.depth
      || (n.depth === best.depth && n.end_page - n.start_page <= best.end_page - best.start_page)) best = n;
  }
  return best;
}

/** Ids to expand so every covering node is visible: each covering node and all its ancestors. */
export function expandedFor(nodes: TreeNode[], page: number): Set<string> {
  const parent = new Map(nodes.map((n) => [n.node_id, n.parent_id]));
  const out = new Set<string>();
  for (const n of nodes) {
    if (!covers(n, page)) continue;
    let id: string | null | undefined = n.node_id;
    while (id && parent.has(id) && !out.has(id)) {
      out.add(id);
      id = parent.get(id);
    }
  }
  return out;
}
