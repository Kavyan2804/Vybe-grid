'use client';

import React, { useEffect, useState } from 'react';
import { BadgeGroup } from '../../components/badges';
import { Panel, PanelState } from '../../components/panels/Panel';
import { apiGet, ApiError, DEFAULT_SITE_ID } from '../../lib/api';

interface SavingsMetrics {
  diesel_hours: number;
  diesel_energy_kwh: number;
  fuel_litres: number;
  cost: number;
  co2_kg: number;
}

type SavingsDeltaMetrics = SavingsMetrics;

interface SavingsResponse {
  comparison: unknown;
  optimized: SavingsMetrics;
  baseline: SavingsMetrics;
  saved: SavingsDeltaMetrics;
}

function Row({ label, optimized, baseline, saved, unit }: { label: string; optimized: number; baseline: number; saved: number; unit: string }) {
  return (
    <tr className="border-b border-slate-50">
      <td className="py-2 pr-4 text-slate-600 font-sans text-[13px]">{label}</td>
      <td className="py-2 pr-4 font-mono text-[13px] text-slate-900">
        {optimized.toFixed(1)} {unit}
      </td>
      <td className="py-2 pr-4 font-mono text-[13px] text-slate-500">
        {baseline.toFixed(1)} {unit}
      </td>
      <td className="py-2 font-mono text-[13px] font-bold text-[#0B6E4F]">
        {saved.toFixed(1)} {unit}
      </td>
    </tr>
  );
}

/**
 * Savings — PHASE_4 Task 4.3. Reads GET /api/savings for the selected range: the measured
 * delta between the optimized run and the shadow baseline over identical conditions
 * (PRD.md USP 1). Requires both ledgers to have data for the range — a range with no
 * overlap between the two renders the panel's empty state, never a fabricated zero.
 */
export default function SavingsPage() {
  const [state, setState] = useState<PanelState>('loading');
  const [data, setData] = useState<SavingsResponse | null>(null);
  const [hoursBack, setHoursBack] = useState(24);

  const load = () => {
    setState('loading');
    const end = new Date();
    const start = new Date(end.getTime() - hoursBack * 3600_000);
    apiGet<SavingsResponse>('savings', {
      site_id: DEFAULT_SITE_ID,
      start_at: start.toISOString(),
      end_at: end.toISOString(),
    })
      .then((res) => {
        setData(res);
        setState('ready');
      })
      .catch((err: unknown) => {
        // A 404 here most often means "no plan/telemetry in this range yet" —
        // that's an empty range, not a broken panel.
        setData(null);
        setState(err instanceof ApiError && err.status === 404 ? 'empty' : 'error');
      });
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoursBack]);

  return (
    <main className="w-full pt-20 pb-12 px-4 md:px-6 max-w-[1720px] mx-auto flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="font-sans text-[20px] font-bold text-slate-900">Savings vs Baseline</h1>
        <select
          id="savings-range"
          value={hoursBack}
          onChange={(e) => setHoursBack(Number(e.target.value))}
          className="font-sans text-[12px] border border-slate-200 rounded px-2 py-1 bg-white"
        >
          <option value={24}>Last 24 hours</option>
          <option value={72}>Last 3 days</option>
          <option value={168}>Last 7 days</option>
        </select>
      </div>

      <Panel
        title="Optimized vs greedy baseline, identical conditions"
        state={state}
        emptyMessage="No dispatch plan or telemetry recorded for this range yet"
        onRetry={load}
        badge={<BadgeGroup kinds={['SIMULATED', 'BASELINE']} />}
      >
        {data && (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-slate-400 font-sans text-[11px] uppercase tracking-wide border-b border-slate-100">
                  <th className="py-1 pr-4">Metric</th>
                  <th className="py-1 pr-4">GridPilot</th>
                  <th className="py-1 pr-4">Greedy baseline</th>
                  <th className="py-1">Saved</th>
                </tr>
              </thead>
              <tbody>
                <Row label="Diesel hours" optimized={data.optimized.diesel_hours} baseline={data.baseline.diesel_hours} saved={data.saved.diesel_hours} unit="h" />
                <Row label="Fuel" optimized={data.optimized.fuel_litres} baseline={data.baseline.fuel_litres} saved={data.saved.fuel_litres} unit="L" />
                <Row label="Cost" optimized={data.optimized.cost} baseline={data.baseline.cost} saved={data.saved.cost} unit="" />
                <Row label="CO2" optimized={data.optimized.co2_kg} baseline={data.baseline.co2_kg} saved={data.saved.co2_kg} unit="kg" />
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </main>
  );
}
