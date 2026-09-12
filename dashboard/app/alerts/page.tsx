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

export default async function AlertsPage() {
  const response = await getAlerts();
  const alerts = response?.items ?? [];

  return (
    <main className="dashboard-shell alerts-shell">
      <section className="alerts-panel">
        <div className="alerts-heading">
          <div className="alerts-title-group">
            <h1>Operational Alerts &amp; Notices</h1>
            <span className="alert-status live">LIVE</span>
            <span className="alert-active-count">{response?.total ?? 0} Active</span>
          </div>
        </div>

        <div className="alert-list">
          {alerts.length ? alerts.map((alert) => (
            <article className={`alert-card alert-card-${alert.severity}`} key={alert.id}>
              <div className="alert-icon" aria-hidden="true">{alert.severity === 'warning' ? '!' : 'i'}</div>
              <div className="alert-card-content">
                <div className="alert-card-title">
                  <h2>{alert.title}</h2>
                  <span className={`alert-status ${alert.status === 'acknowledged' ? 'forecast' : 'live'}`}>
                    {alert.status.toUpperCase()}
                  </span>
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
          )) : (
            <p className="alerts-data-note">
              {response ? 'No active alerts for Dharavi Microgrid.' : 'Live alerts are temporarily unavailable.'}
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
