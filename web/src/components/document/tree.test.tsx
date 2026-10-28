import { describe, expect, it } from 'vitest';
import type { TreeNode } from '../../api/client';
import { buildTree, coveringNodes, deepestCovering, expandedFor } from './tree';

const node = (node_id: string, parent_id: string | null, depth: number, start_page: number, end_page: number): TreeNode => ({
  node_id, parent_id, depth, title: node_id, start_page, end_page, page_label_range: null, section_type: null, concepts: [],
});

const NODES = [
  node('a', null, 1, 1, 3),
  node('a1', 'a', 2, 1, 2),
  node('a2', 'a', 2, 3, 3),
  node('b', null, 1, 4, 20),
  node('b1', 'b', 2, 4, 10),
  node('b1x', 'b1', 3, 6, 8),
  node('orphan', 'missing', 2, 30, 30),
];

describe('buildTree', () => {
  it('nests flat nodes by parent_id in input order', () => {
    const roots = buildTree(NODES);
    expect(roots.map((n) => n.node_id)).toEqual(['a', 'b', 'orphan']);
    expect(roots[0].children.map((n) => n.node_id)).toEqual(['a1', 'a2']);
    expect(roots[1].children[0].children.map((n) => n.node_id)).toEqual(['b1x']);
    expect(roots[2].children).toEqual([]);
  });
});

describe('covering nodes', () => {
  it('finds every node whose page range contains the page, shallowest first', () => {
    expect(coveringNodes(NODES, 7).map((n) => n.node_id)).toEqual(['b', 'b1', 'b1x']);
    expect(coveringNodes(NODES, 3).map((n) => n.node_id)).toEqual(['a', 'a2']);
    expect(coveringNodes(NODES, 25)).toEqual([]);
  });

  it('picks the deepest covering node', () => {
    expect(deepestCovering(NODES, 7)?.node_id).toBe('b1x');
    expect(deepestCovering(NODES, 12)?.node_id).toBe('b');
    expect(deepestCovering(NODES, 25)).toBeNull();
  });

  it('prefers the narrower node at the same depth', () => {
    const nodes = [node('wide', null, 1, 1, 50), node('narrow', null, 1, 5, 6)];
    expect(deepestCovering(nodes, 5)?.node_id).toBe('narrow');
  });

  it('expands covering nodes and their ancestors', () => {
    expect([...expandedFor(NODES, 7)].sort()).toEqual(['b', 'b1', 'b1x']);
    expect([...expandedFor(NODES, 30)].sort()).toEqual(['orphan']);
  });
});
