// View 2: retrieval trace. Without an id, the recent traced tool calls; with one, that call's request, results,
// gaps, per-route ranks, coverage gate, tier decisions and the final DSL/SQL per template.
import { ApiError, api } from '../api/client';
import { ErrorBanner, Link, Loading } from '../components/Shared';
import { TraceDetailView } from '../components/trace/TraceDetail';
import { TraceList } from '../components/trace/TraceList';
import '../components/trace/trace.css';
import { useAsync } from '../lib/hooks';

export function TraceView({ traceId }: { traceId?: string }) {
  return (
    <section className="view" data-view="trace">
      {traceId ? <OneTrace traceId={traceId} /> : (
        <>
          <div className="tr-head"><h1>Retrieval trace</h1><span className="muted">Recent tool calls</span></div>
          <TraceList />
        </>
      )}
    </section>
  );
}

function OneTrace({ traceId }: { traceId: string }) {
  const { data, error, loading } = useAsync(() => api.trace(traceId), [traceId]);
  const notFound = error instanceof ApiError && error.status === 404;
  return (
    <>
      <div className="tr-head">
        <h1>Trace <span className="mono">{traceId}</span></h1>
        <Link to={{ view: 'trace' }}>All traces</Link>
      </div>
      {loading && <Loading what="trace" />}
      {notFound ? <ErrorBanner error={`No trace with id ${traceId}.`} /> : <ErrorBanner error={error} />}
      {data && !loading && <TraceDetailView trace={data} />}
    </>
  );
}
