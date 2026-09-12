import { Badge } from '../../components/badges';
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
  const metrics = [
    ['Cost Avoided', `Rs ${Math.round(Math.abs(saved?.cost ?? 0)).toLocaleString('en-IN')}`, 'vs diesel baseline'],
    ['Fuel Saved', signed(saved?.fuel_litres, ' L'), 'today'],
    ['CO2 Avoided', signed(saved?.co2_kg, ' kg'), 'estimated'],
    ['Diesel Runtime', signed(saved?.diesel_hours, ' h'), 'avoided'],
  ];

  return (
    <main className="dashboard-shell">
      <div className="page-kicker">Savings Analysis</div>
      <h1>Baseline Comparison</h1>
      <div className="metric-grid">
        {metrics.map(([label, value, note]) => (
          <Panel key={label} title={label} action={<Badge tone="baseline">BASELINE</Badge>}>
            <div className="metric-card-value">{value}</div>
            <p className="muted">{note}</p>
          </Panel>
        ))}
      </div>
      <Panel title="Savings Drivers" eyebrow="Solar-first dispatch">
        {savings ? (
          <div className="savings-bars">
            <div><span>Optimized diesel cost</span><i style={{ width: `${Math.min(100, Math.max(8, savings.optimized.cost / Math.max(1, savings.baseline.cost) * 100))}%` }} /></div>
            <div><span>Optimized fuel burn</span><i style={{ width: `${Math.min(100, Math.max(8, savings.optimized.fuel_litres / Math.max(1, savings.baseline.fuel_litres) * 100))}%` }} /></div>
            <div><span>Plan comparison hours</span><i style={{ width: `${Math.min(100, Math.max(8, savings.comparison.hours.length * 8))}%` }} /></div>
          </div>
        ) : (
          <p className="muted">The backend is connected, but savings need matching optimized and baseline telemetry for today's range.</p>
        )}
      </Panel>
    </main>
  );
}
