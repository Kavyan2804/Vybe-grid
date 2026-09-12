import { Badge, BadgeGroup } from '../../components/badges';
import { Panel } from '../../components/panels/Panel';
import { gridpilotFetch, siteQuery, type SavingsResponse } from '../../lib/api';

async function getSavings() {
  const end = new Date();
  const start = new Date(end);
  start.setHours(0, 0, 0, 0);

  try {
    return await gridpilotFetch<SavingsResponse>(
      `/savings?${siteQuery()}&start_at=${encodeURIComponent(start.toISOString())}&end_at=${encodeURIComponent(end.toISOString())}`,
    );
  } catch {
    return null;
  }
}

function signed(value = 0, unit = '') {
  const abs = Math.abs(value);
  return `${value >= 0 ? '' : '-'}${abs.toLocaleString('en-IN', { maximumFractionDigits: 1 })}${unit}`;
}

export default async function SavingsPage() {
  const savings = await getSavings();
  const saved = savings?.saved;
  const hasData = Boolean(savings);
  const metrics = [
    ['Cost Avoided', `Rs ${Math.round(Math.abs(saved?.cost ?? 0)).toLocaleString('en-IN')}`, 'vs diesel baseline'],
    ['Fuel Saved', signed(saved?.fuel_litres, ' L'), 'today'],
    ['CO2 Avoided', signed(saved?.co2_kg, ' kg'), 'estimated'],
    ['Diesel Runtime', signed(saved?.diesel_hours, ' h'), 'avoided'],
  ];

  const pairs = savings
    ? [
        ['Diesel hours', savings.optimized.diesel_hours, savings.baseline.diesel_hours],
        ['Fuel (L)', savings.optimized.fuel_litres, savings.baseline.fuel_litres],
        ['Cost', savings.optimized.cost, savings.baseline.cost],
        ['CO₂ (kg)', savings.optimized.co2_kg, savings.baseline.co2_kg],
      ] as const
    : [];

  return (
    <main className="dashboard-shell">
      <div className="page-kicker">Savings Analysis</div>
      <h1>Baseline Comparison</h1>
      <div className="metric-grid">
        {metrics.map(([label, value, note]) => (
          <Panel
            key={label}
            title={label}
            action={<BadgeGroup kinds={['SIMULATED', 'BASELINE']} />}
            state={hasData ? 'ready' : 'empty'}
          >
            <div className="metric-card-value">{hasData ? value : '—'}</div>
            <p className="muted">{note}</p>
          </Panel>
        ))}
      </div>
      <Panel
        title="Optimized vs baseline"
        eyebrow="Paired bars use identical realized conditions"
        state={hasData ? 'ready' : 'empty'}
        action={<Badge kind="BASELINE" />}
        message="Select a range with matching optimized and baseline telemetry to render savings."
      >
        {hasData ? (
          <div className="savings-bars">
            {pairs.map(([label, optimized, baseline]) => {
              const max = Math.max(optimized, baseline, 1);
              return (
                <div key={label} className="savings-pair">
                  <span>
                    {label}: opt {optimized.toFixed(1)} / base {baseline.toFixed(1)}
                  </span>
                  <i style={{ width: `${Math.min(100, Math.max(8, (optimized / max) * 100))}%` }} />
                  <b style={{ width: `${Math.min(100, Math.max(8, (baseline / max) * 100))}%` }} />
                </div>
              );
            })}
          </div>
        ) : null}
      </Panel>
    </main>
  );
}
