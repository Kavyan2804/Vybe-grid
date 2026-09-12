'use client';

import { useCallback, useEffect, useState } from 'react';
import { Badge, BadgeGroup } from '../components/badges';
import { PlanTimelineChart } from '../components/charts/PlanTimelineChart';
import { Panel } from '../components/panels/Panel';
import {
  DEFAULT_SITE_ID,
  gridpilotFetch,
  siteQuery,
  type LatestPlanResponse,
  type OverviewResponse,
} from '../lib/api';
import { createSiteEventStream } from '../lib/sse';

type AlertListResponse = {
  total: number;
  items: Array<{ id: string; title: string; severity: string; message: string }>;
};

function formatValue(value: number | undefined, digits = 1) {
  if (value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString('en-IN', { maximumFractionDigits: digits });
}

export default function OverviewPage() {
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [plan, setPlan] = useState<LatestPlanResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertListResponse | null>(null);
  const [streamStatus, setStreamStatus] = useState<'connected' | 'reconnecting' | 'disconnected'>(
    'reconnecting',
  );
  const [error, setError] = useState<string | null>(null);
  const [tickBusy, setTickBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextOverview, nextPlan, nextAlerts] = await Promise.all([
        gridpilotFetch<OverviewResponse>(`/overview?${siteQuery()}`),
        gridpilotFetch<LatestPlanResponse>(`/plans/latest?${siteQuery()}`).catch(() => null),
        gridpilotFetch<AlertListResponse>(`/alerts/active?${siteQuery()}`).catch(() => null),
      ]);
      setOverview(nextOverview);
      setPlan(nextPlan);
      setAlerts(nextAlerts);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load overview');
    }
  }, []);

  useEffect(() => {
    void load();
    const stream = createSiteEventStream({
      siteId: DEFAULT_SITE_ID,
      onStatus: setStreamStatus,
      onResync: load,
      onEvent: () => {
        void load();
      },
    });
    return () => stream.close();
  }, [load]);

  const runTick = async () => {
    setTickBusy(true);
    try {
      await gridpilotFetch(`/tick?${siteQuery()}`, { method: 'POST' });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tick failed');
    } finally {
      setTickBusy(false);
    }
  };

  const panelState =
    error && !overview
      ? 'error'
      : streamStatus === 'reconnecting' || streamStatus === 'disconnected'
        ? overview
          ? 'stale'
          : 'disconnected'
        : overview
          ? 'ready'
          : 'loading';

  const series = plan?.series ?? [];
  const chartPoints = series.map((point) => {
    const batteryKw = (point.batt_discharge_kw ?? 0) - (point.batt_charge_kw ?? 0);
    return {
      hour: `H${point.hour}`,
      solarKw: point.solar_used_kw ?? 0,
      batteryKw: Math.abs(batteryKw),
      dieselKw: point.diesel_kw ?? 0,
      demandKw: (point.solar_used_kw ?? 0) + Math.max(batteryKw, 0) + (point.diesel_kw ?? 0),
      executed: Boolean(point.executed),
      status: point.executed ? ('live' as const) : ('forecast' as const),
    };
  });

  const current = overview?.current;
  const today = overview?.today;

  return (
    <main className="dashboard-shell">
      <div className="overview-top">
        <div>
          <div className="page-kicker">Operations</div>
          <h1>{overview?.site?.name ?? DEFAULT_SITE_ID}</h1>
        </div>
        <div className="overview-actions">
          <Badge tone={streamStatus === 'connected' ? 'live' : 'danger'}>
            {streamStatus === 'connected' ? 'LIVE STREAM' : 'RECONNECTING'}
          </Badge>
          <button type="button" className="primary-button" onClick={runTick} disabled={tickBusy}>
            {tickBusy ? 'Running tick…' : 'Run tick'}
          </button>
        </div>
      </div>

      <div className="overview-tiles">
        <Panel
          title="Current mix"
          eyebrow="This hour"
          state={current ? panelState : overview ? 'empty' : panelState}
          action={<Badge kind="SIMULATED" />}
        >
          {current ? (
            <div className="metric-list">
              <div><span>Solar</span><strong>{formatValue(current.solar_kw?.value)} kW</strong></div>
              <div><span>Load</span><strong>{formatValue(current.load_kw?.value)} kW</strong></div>
              <div>
                <span>Diesel</span>
                <strong>{current.diesel_on ? 'ON' : 'OFF'}</strong>
              </div>
            </div>
          ) : null}
        </Panel>

        <Panel
          title="Battery SoC"
          eyebrow="Measured twin state"
          state={current ? panelState : overview ? 'empty' : panelState}
          action={<Badge kind="SIMULATED" />}
        >
          {current ? (
            <div className="soc-gauge">
              <div className="metric-card-value">{formatValue(current.soc_pct?.value, 0)}%</div>
              <p className="muted">Reserve band appears once forecast P10/P90 is live.</p>
            </div>
          ) : null}
        </Panel>

        <Panel
          title="Today vs baseline"
          eyebrow="Identical realized conditions"
          state={today ? panelState : overview ? 'empty' : panelState}
          action={<BadgeGroup kinds={['SIMULATED', 'BASELINE']} />}
        >
          {today ? (
            <div className="metric-list">
              <div>
                <span>Diesel hours</span>
                <strong>{formatValue(today.diesel_hours?.value)} h</strong>
              </div>
              <div>
                <span>Fuel saved</span>
                <strong>
                  {today.fuel_liters_saved_vs_baseline
                    ? `${formatValue(today.fuel_liters_saved_vs_baseline.value)} L`
                    : '—'}
                </strong>
              </div>
              <div>
                <span>Cost saved</span>
                <strong>
                  {today.cost_saved_vs_baseline
                    ? `Rs ${formatValue(today.cost_saved_vs_baseline.value, 0)}`
                    : '—'}
                </strong>
              </div>
            </div>
          ) : null}
        </Panel>
      </div>

      <Panel
        title="24h dispatch plan"
        eyebrow={plan ? `solver ${plan.solver_status ?? 'unknown'}` : 'awaiting first tick'}
        state={series.length ? panelState : overview ? 'empty' : panelState}
        action={<Badge kind="FORECAST" />}
        message={error ?? undefined}
      >
        <PlanTimelineChart points={chartPoints} />
      </Panel>

      <Panel
        title="Alerts"
        eyebrow={`${alerts?.total ?? overview?.unread_alerts ?? 0} open`}
        state={alerts ? panelState : overview ? 'empty' : panelState}
        action={<Badge kind="SIMULATED" />}
      >
        <div className="alert-list">
          {(alerts?.items ?? []).slice(0, 5).map((alert) => (
            <article className="alert-row" key={alert.id}>
              <Badge tone={alert.severity === 'critical' ? 'danger' : 'baseline'}>{alert.severity}</Badge>
              <div>
                <h3>{alert.title}</h3>
                <p>{alert.message}</p>
              </div>
            </article>
          ))}
          {!alerts?.items?.length ? <p className="muted">No open alerts.</p> : null}
        </div>
      </Panel>
    </main>
  );
}
