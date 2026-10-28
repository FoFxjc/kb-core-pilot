import { describe, expect, it } from 'vitest';
import { href, parse } from './router';

describe('router', () => {
  it('parses the three views and deep links', () => {
    expect(parse('/ui/')).toEqual({ view: 'chat', replay: undefined });
    expect(parse('/ui/chat', '?replay=mcp_demo_round1')).toEqual({ view: 'chat', replay: 'mcp_demo_round1' });
    expect(parse('/ui/chat', '?mode=live')).toEqual({ view: 'chat', live: true, session: undefined });
    expect(parse('/ui/trace/tr_abc')).toEqual({ view: 'trace', traceId: 'tr_abc' });
    expect(parse('/ui/docs/ocbc-group_ar_2025_en/pages/98')).toEqual({
      view: 'document', docId: 'ocbc-group_ar_2025_en', page: 98 });
    expect(parse('/ui/docs/d/pages/x')).toEqual({ view: 'document', docId: 'd', page: undefined });
  });

  it('builds links that parse back to the same route', () => {
    for (const r of [{ view: 'trace', traceId: 'tr_1' }, { view: 'document', docId: 'a b', page: 3 },
      { view: 'chat', replay: 'x' }, { view: 'chat', live: true, session: 'chat_1' }] as const) {
      const url = new URL(href(r), 'http://h');
      expect(parse(url.pathname, url.search)).toEqual(r);
    }
  });
});
