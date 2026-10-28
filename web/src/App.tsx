import { Chat } from './pages/Chat';
import { DocumentView } from './pages/Document';
import { TraceView } from './pages/Trace';
import { Link } from './components/Shared';
import { href, navigate, useRoute, type Route } from './lib/router';
import { useEffect } from 'react';
import { api } from './api/client';
import { ROLES, setPickerEnabled, setSubject, usePickerEnabled, useSubject, type Role } from './lib/subject';

const TABS: { view: Route['view']; label: string; to: Route }[] = [
  { view: 'chat', label: 'Chat', to: { view: 'chat' } },
  { view: 'trace', label: 'Retrieval trace', to: { view: 'trace' } },
  { view: 'document', label: 'Document & evidence', to: { view: 'document' } },
];

/** Dev control: the role every request runs as. A live chat session keeps the subject it started with, so a role
 * change leaves an open session for a new one. */
function RolePicker({ route }: { route: Route }) {
  const subject = useSubject();
  const change = (role: Role) => {
    setSubject(role);
    if (route.view === 'chat' && route.live && new URLSearchParams(window.location.search).has('session')) {
      navigate(href({ view: 'chat', live: true }));
    }
  };
  return (
    <div className="role-picker" title="Development control: the access role sent as X-KB-Subject">
      <span className="badge role-dev">dev</span>
      <label htmlFor="role-picker">Viewing as</label>
      <select id="role-picker" value={subject} onChange={(e) => change(e.target.value as Role)}>
        {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
    </div>
  );
}

export function App() {
  const route = useRoute();
  const subject = useSubject();
  const picker = usePickerEnabled();
  useEffect(() => {
    // the server says whether a dev role picker exists (auth mode none); hidden when unknown or behind the gateway
    api.config().then((c) => setPickerEnabled(c.role_picker === true)).catch(() => setPickerEnabled(false));
  }, []);
  return (
    <div className="app">
      <header className="app-header">
        <span className="brand">kb-core</span>
        <nav>
          {TABS.map((t) => (
            <Link key={t.view} to={t.to} className={route.view === t.view ? 'tab active' : 'tab'}>
              {t.label}
            </Link>
          ))}
        </nav>
        {picker && <RolePicker route={route} />}
      </header>
      {/* Keyed by the subject: a role change remounts the view, so it re-fetches what that role sees. */}
      <main className="app-main" key={picker ? subject : 'gateway'}>
        {route.view === 'chat' && <Chat replay={route.replay} live={route.live} session={route.session} />}
        {route.view === 'trace' && <TraceView traceId={route.traceId} />}
        {route.view === 'document' && <DocumentView docId={route.docId} page={route.page} />}
      </main>
    </div>
  );
}
