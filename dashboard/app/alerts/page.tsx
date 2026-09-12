import { Badge } from '../../components/badges';
import { Panel } from '../../components/panels/Panel';
import { gridpilotFetch, siteQuery } from '../../lib/api';

type AlertItem = {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  status: string;
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
      <Panel title="Active Alert Queue" eyebrow={`${response?.total ?? 0} require operator review`}>
        <div className="alert-list">
          {alerts.map((alert) => (
            <article className="alert-row" key={alert.id}>
              <Badge tone={alert.severity === 'critical' ? 'danger' : alert.severity === 'info' ? 'live' : 'baseline'}>{alert.severity}</Badge>
              <div>
                <h3>{alert.title}</h3>
                <p>{alert.message}</p>
              </div>
            </article>
          ))}
          {!alerts.length ? (
            <article className="alert-row">
              <Badge tone={response ? 'live' : 'danger'}>{response ? 'CLEAR' : 'OFFLINE'}</Badge>
              <div>
                <h3>{response ? 'No active alerts' : 'Alerts API unavailable'}</h3>
                <p>{response ? 'The backend returned an empty active alert queue.' : 'Could not load active alerts from the backend.'}</p>
              </div>
            </article>
          ) : null}
        </div>
      </Panel>
    </main>
  );
}
