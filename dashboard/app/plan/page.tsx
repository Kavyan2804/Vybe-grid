import { Badge } from '../../components/badges';
import { PlanTimelineChart } from '../../components/charts/PlanTimelineChart';
import { Panel } from '../../components/panels/Panel';
import {
  DEFAULT_SITE_ID,
  gridpilotFetch,
  siteQuery,
  type LatestPlanResponse,
} from '../../lib/api';

type TelemetryPoint = {
  at: string;
  solar_kw: number;
  load_kw: number;
  diesel_kw: number;
  batt_kw: number;
};

type TelemetryResponse = {
  items?: TelemetryPoint[];
  points?: TelemetryPoint[];
};

function formatKw(value = 0) {
  return `${value.toFixed(1)} kW`;
}

async function getPlan() {
  try {
    return await gridpilotFetch<LatestPlanResponse>(`/plans/latest?${siteQuery()}`);
  } catch {
    return null;
  }
}

async function getTelemetry() {
  try {
    return await gridpilotFetch<TelemetryResponse>(`/telemetry/latest?${siteQuery()}&limit=24`);
  } catch {
    try {
      return await gridpilotFetch<TelemetryResponse>(`/telemetry?${siteQuery()}&limit=24`);
    } catch {
      return null;
    }
  }
}

export default async function PlanPage() {
  const [plan, telemetry] = await Promise.all([getPlan(), getTelemetry()]);
  const series = plan?.series ?? [];
  const actuals = telemetry?.items ?? telemetry?.points ?? [];

  const chartPoints = series.map((point, index) => {
    const batteryKw = (point.batt_discharge_kw ?? 0) - (point.batt_charge_kw ?? 0);
    const actual = actuals[index];
    const plannedDemand =
      (point.solar_used_kw ?? 0) + Math.max(batteryKw, 0) + (point.diesel_kw ?? 0);
    return {
      hour: `H${point.hour}`,
      solarKw: point.solar_used_kw ?? 0,
      batteryKw: Math.abs(batteryKw),
      dieselKw: point.diesel_kw ?? 0,
      demandKw: actual ? actual.load_kw : plannedDemand,
      executed: Boolean(point.executed),
      status: point.executed ? ('live' as const) : ('forecast' as const),
    };
  });

  const gapRows = series
    .filter((point) => point.executed)
    .map((point, index) => {
      const actual = actuals[index];
      if (!actual) return null;
      const plannedSolar = point.solar_used_kw ?? 0;
      return {
        hour: point.hour,
        solarGap: actual.solar_kw - plannedSolar,
        loadGap: actual.load_kw - ((point.solar_used_kw ?? 0) + (point.diesel_kw ?? 0)),
      };
    })
    .filter(Boolean);

  return (
    <main className="dashboard-shell">
      <div className="page-kicker">Dispatch Plan</div>
      <h1>Plan vs Actual</h1>
      <div className="dashboard-grid">
        <Panel
          title="24 Hour Dispatch"
          eyebrow={`${DEFAULT_SITE_ID} — ${plan ? `solver ${plan.solver_status ?? 'unknown'}` : 'backend unavailable'}`}
          action={
            <Badge tone={plan?.solver_status === 'optimal' ? 'live' : 'forecast'}>
              {plan?.solver_status ?? 'OFFLINE'}
            </Badge>
          }
          state={series.length ? 'ready' : 'empty'}
        >
          <PlanTimelineChart points={chartPoints} />
        </Panel>
        <Panel title="Forecast error gap" eyebrow="Executed hours only" action={<Badge kind="SIMULATED" />}>
          <div className="metric-list">
            {gapRows.length ? (
              gapRows.map((row) =>
                row ? (
                  <div key={row.hour}>
                    <span>H{row.hour}</span>
                    <strong>
                      solar {row.solarGap >= 0 ? '+' : ''}
                      {row.solarGap.toFixed(1)} kW
                    </strong>
                  </div>
                ) : null,
              )
            ) : (
              <p className="muted">Run ticks to compare executed hours against the plan.</p>
            )}
          </div>
        </Panel>
      </div>
      <Panel title="Dispatch Slots" state={series.length ? 'ready' : 'empty'}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Hour</th>
                <th>Solar</th>
                <th>Battery</th>
                <th>Diesel</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {series.map((point) => (
                <tr key={point.hour}>
                  <td>H{point.hour}</td>
                  <td>{formatKw(point.solar_used_kw)}</td>
                  <td>{formatKw((point.batt_discharge_kw ?? 0) - (point.batt_charge_kw ?? 0))}</td>
                  <td>{formatKw(point.diesel_kw)}</td>
                  <td>
                    <Badge tone={point.executed ? 'live' : 'forecast'}>
                      {point.executed ? 'Executed' : 'Forecast'}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!series.length ? <p className="muted">No dispatch plan has been produced yet.</p> : null}
        </div>
      </Panel>
    </main>
  );
}
