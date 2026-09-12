import { Badge } from '../../components/badges';
import { PlanTimelineChart } from '../../components/charts/PlanTimelineChart';
import { Panel } from '../../components/panels/Panel';
import { DEFAULT_SITE_ID, gridpilotFetch, siteQuery, type LatestPlanResponse } from '../../lib/api';

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

export default async function PlanPage() {
  const plan = await getPlan();
  const series = plan?.series ?? [];
  const chartPoints = series.map((point) => {
    const batteryKw = (point.batt_discharge_kw ?? 0) - (point.batt_charge_kw ?? 0);
    return {
      hour: `H${point.hour}`,
      solarKw: point.solar_used_kw ?? 0,
      batteryKw: Math.abs(batteryKw),
      dieselKw: point.diesel_kw ?? 0,
      demandKw: (point.solar_used_kw ?? 0) + Math.max(batteryKw, 0) + (point.diesel_kw ?? 0),
      status: point.executed ? 'live' as const : 'forecast' as const,
    };
  });

  return (
    <main className="dashboard-shell">
      <div className="page-kicker">Dispatch Plan</div>
      <h1>Plan vs Actual</h1>
      <div className="dashboard-grid">
        <Panel
          title="24 Hour Dispatch"
          eyebrow={`${DEFAULT_SITE_ID} - ${plan ? `solver ${plan.solver_status ?? 'unknown'} in ${((plan.solve_ms ?? 0) / 1000).toFixed(2)}s` : 'backend unavailable'}`}
          action={<Badge tone={plan?.solver_status === 'optimal' ? 'live' : 'forecast'}>{plan?.solver_status ?? 'OFFLINE'}</Badge>}
        >
          <PlanTimelineChart points={chartPoints.length ? chartPoints : undefined} />
        </Panel>
        <Panel title="Operating Guardrails" eyebrow="Next replan in 27m">
          <div className="metric-list">
            <div><span>Minimum SOC</span><strong>20%</strong></div>
            <div><span>Starting SOC</span><strong>{formatKw(plan?.starting_soc_kwh).replace('kW', 'kWh')}</strong></div>
            <div><span>Diesel Starts</span><strong>{series.filter((point) => point.diesel_on).length}</strong></div>
            <div><span>Objective Cost</span><strong>Rs {Math.round(plan?.objective_cost ?? 0).toLocaleString('en-IN')}</strong></div>
          </div>
        </Panel>
      </div>
      <Panel title="Dispatch Slots">
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
                  <td><Badge tone={point.executed ? 'live' : 'forecast'}>{point.executed ? 'Executed' : 'Forecast'}</Badge></td>
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
