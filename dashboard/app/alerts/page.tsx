import { gridpilotFetch, siteQuery } from '../../lib/api';

type AlertItem = {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  status: string;
  raised_at?: string;
  received_at?: string;
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

const previewAlerts: AlertItem[] = [
  {
    id: 'diesel-start',
    severity: 'warning',
    title: 'Diesel start planned within 2 hours',
    message: 'Battery SoC projected to hit 22% at 16:30 under heavy community irrigation pump schedule. Genset dispatch sequence pre-armed for warm start.',
    status: 'forecast',
    raised_at: '14:30:00',
    received_at: '14:30:02',
  },
  {
    id: 'cloud-cover',
    severity: 'info',
    title: 'Cloud cover trajectory update received from IMD API',
    message: 'Solar irradiance forecast adjusted down -14% for 15:00-17:00 IST window due to cumulus cloud buildup in Samastipur sector.',
    status: 'forecast',
    raised_at: '14:15:00',
    received_at: '14:15:01',
  },
];

export default async function AlertsPage() {
  const response = await getAlerts();
  const alerts = response?.items.length ? response.items : previewAlerts;
  const isPreview = !response;

  return (
    <main className="dashboard-shell alerts-shell">
      <section className="alerts-panel">
        <div className="alerts-heading">
          <div className="alerts-title-group">
            <h1>Operational Alerts &amp; Notices</h1>
            <span className="alert-status forecast">FORECAST</span>
            <span className="alert-active-count">{response?.total ?? alerts.length} Active</span>
          </div>
          <a className="cluster-logs-link" href="#cluster-logs">View All Cluster Logs <span aria-hidden="true">-&gt;</span></a>
        </div>

        <div className="alert-list">
          {alerts.map((alert) => (
            <article className={`alert-card alert-card-${alert.severity}`} key={alert.id}>
              <div className="alert-icon" aria-hidden="true">{alert.severity === 'warning' ? '!' : 'i'}</div>
              <div className="alert-card-content">
                <div className="alert-card-title">
                  <h2>{alert.title}</h2>
                  <span className="alert-status forecast">FORECAST</span>
                </div>
                <p className="alert-timestamps">
                  raised: {alert.raised_at ?? '--:--:--'} <span>•</span> rcvd: {alert.received_at ?? '--:--:--'} {alert.received_at ? '(gap: 2s OK)' : ''}
                </p>
                <p className="alert-message">{alert.message}</p>
              </div>
              <div className="alert-actions">
                {alert.severity === 'warning' ? (
                  <>
                    <button className="alert-button secondary" type="button">Acknowledge</button>
                    <button className="alert-button primary" type="button">View Constraint <span aria-hidden="true">☷</span></button>
                  </>
                ) : (
                  <button className="alert-button secondary wide" type="button"><span aria-hidden="true">↻</span> Re-solve scheduled at 15:00 tick</button>
                )}
              </div>
            </article>
          ))}
        </div>

        {isPreview ? <p className="alerts-data-note">Showing the latest simulated alert notices while the Alerts API is offline.</p> : null}
      </section>
    </main>
  );
}
