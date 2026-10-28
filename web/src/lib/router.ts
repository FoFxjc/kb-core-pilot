// A small path router for the three views under /ui/ (no dependency). Links push history entries; the server
// answers every /ui/... path with index.html, so deep links work on reload.
import { useEffect, useState } from 'react';

export const BASE = '/ui';

export type Route =
  | { view: 'chat'; replay?: string; live?: boolean; session?: string }
  | { view: 'trace'; traceId?: string }
  | { view: 'document'; docId?: string; page?: number };

export function parse(pathname: string, search = ''): Route {
  const path = pathname.startsWith(BASE) ? pathname.slice(BASE.length) : pathname;
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  const params = new URLSearchParams(search);
  if (parts[0] === 'trace') return { view: 'trace', traceId: parts[1] };
  if (parts[0] === 'docs') {
    const page = parts[2] === 'pages' && /^\d+$/.test(parts[3] ?? '') ? Number(parts[3]) : undefined;
    return { view: 'document', docId: parts[1], page };
  }
  if (params.get('mode') === 'live') return { view: 'chat', live: true, session: params.get('session') ?? undefined };
  return { view: 'chat', replay: params.get('replay') ?? undefined };
}

export function href(route: Route): string {
  switch (route.view) {
    case 'trace':
      return `${BASE}/trace${route.traceId ? `/${encodeURIComponent(route.traceId)}` : ''}`;
    case 'document':
      if (!route.docId) return `${BASE}/docs`;
      return `${BASE}/docs/${encodeURIComponent(route.docId)}${route.page ? `/pages/${route.page}` : ''}`;
    default:
      if (route.live) return `${BASE}/chat?mode=live${route.session ? `&session=${encodeURIComponent(route.session)}` : ''}`;
      return `${BASE}/chat${route.replay ? `?replay=${encodeURIComponent(route.replay)}` : ''}`;
  }
}

export function navigate(to: string): void {
  window.history.pushState(null, '', to);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.pathname, window.location.search));
  useEffect(() => {
    const onPop = () => setRoute(parse(window.location.pathname, window.location.search));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  return route;
}

/** Same-app link: plain <a href> that navigates without a reload (modifier clicks keep browser behaviour). */
export function onLinkClick(e: React.MouseEvent<HTMLAnchorElement>): void {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  e.preventDefault();
  navigate(e.currentTarget.getAttribute('href') ?? BASE);
}
