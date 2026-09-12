import { Badge } from '../../components/badges';
import { Panel } from '../../components/panels/Panel';
import { gridpilotFetch, siteQuery, type SavingsResponse } from '../../lib/api';

async function getSavings() {
  const end = new Date();
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(end).reduce<Record<string, string>>((result, part) => {
    if (part.type !== 'literal') result[part.type] = part.value;
    return result;
  }, {});
  const start = new Date(Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
  ) - (5.5 * 60 * 60 * 1000));

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
  return `${value < 0 ? '-' : ''}${abs.toLocaleString('en-IN', { maximumFractionDigits: 1 })}${unit}`;
}

function signedCurrency(value = 0) {
  return `${value < 0 ? '-' : ''}Rs ${Math.round(Math.abs(value)).toLocaleString('en-IN')}`;
}

export default async function SavingsPage() {
  const savings = await getSavings();
  const saved = savings?.saved;
  const metrics = [
    ['Cost Avoided', signedCurrency(saved?.cost), saved?.cost != null && saved.cost < 0 ? 'over diesel baseline' : 'vs diesel baseline'],
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
            <div><span>Optimized diesel cost</span><i style={{ width: `${Math.min(100, Math.max(8, savings.baseline.cost ? savings.optimized.cost / savings.baseline.cost * 100 : savings.optimized.cost > 0 ? 100 : 8))}%` }} /></div>
            <div><span>Optimized fuel burn</span><i style={{ width: `${Math.min(100, Math.max(8, savings.baseline.fuel_litres ? savings.optimized.fuel_litres / savings.baseline.fuel_litres * 100 : savings.optimized.fuel_litres > 0 ? 100 : 8))}%` }} /></div>
            <div><span>Plan comparison hours</span><i style={{ width: `${Math.min(100, Math.max(8, savings.comparison.hours.length * 8))}%` }} /></div>
          </div>
        ) : (
          <p className="muted">The backend is connected, but savings need matching optimized and baseline telemetry for today's range.</p>
        )}
      </Panel>
    </main>
  );
}
