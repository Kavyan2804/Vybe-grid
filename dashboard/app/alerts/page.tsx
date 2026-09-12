import { Badge } from '../../components/badges';
import { Panel } from '../../components/panels/Panel';
import { gridpilotFetch, siteQuery } from '../../lib/api';

type AlertItem = {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  status: string;
  state?: string;
  raised_at?: string;
  received_at?: string;
  type?: string;
};

type AlertListResponse = {
  total: number;
  items: AlertItem[];
};

async function getAlerts() {
  try {
    return await gridpilotFetch<AlertListResponse>(`/alerts/active?${siteQuery()}`);
  } catch {
    return null;
  }
}

export default async function AlertsPage() {
  const response = await getAlerts();
  const alerts = response?.items ?? [];

  return (
    <main className="dashboard-shell">
      <div className="page-kicker">Alerts</div>
      <h1>Operational Exceptions</h1>
      <Panel
        title="Active Alert Queue"
        eyebrow={`${response?.total ?? 0} require operator review`}
        state={response ? (alerts.length ? 'ready' : 'empty') : 'error'}
        action={<Badge kind="SIMULATED" />}
      >
        <div className="alert-list">
          {alerts.map((alert) => {
            const raised = alert.raised_at ? Date.parse(alert.raised_at) : NaN;
            const received = alert.received_at ? Date.parse(alert.received_at) : NaN;
            const gapSec =
              Number.isFinite(raised) && Number.isFinite(received)
                ? Math.max(0, Math.round((received - raised) / 1000))
                : null;
            return (
              <article className="alert-row" key={alert.id}>
                <Badge tone={alert.severity === 'critical' ? 'danger' : alert.severity === 'info' ? 'live' : 'baseline'}>
                  {alert.type ?? alert.severity}
                </Badge>
                <div>
                  <h3>{alert.title}</h3>
                  <p>{alert.message}</p>
                  <p className="muted">
                    raised {alert.raised_at ?? '—'} · received {alert.received_at ?? '—'}
                    {gapSec !== null && gapSec > 3 ? ` · gap ${gapSec}s` : ''}
                  </p>
                </div>
              </article>
            );
          })}
          {!alerts.length ? (
            <article className="alert-row">
              <Badge tone={response ? 'live' : 'danger'}>{response ? 'CLEAR' : 'OFFLINE'}</Badge>
              <div>
                <h3>{response ? 'No active alerts' : 'Alerts API unavailable'}</h3>
                <p>
                  {response
                    ? 'The backend returned an empty active alert queue.'
                    : 'Could not load active alerts from the backend.'}
                </p>
              </div>
            </article>
          ) : null}
        </div>
      </Panel>
    </main>
  );
}
