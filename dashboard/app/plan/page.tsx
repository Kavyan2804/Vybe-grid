'use client';

import React, { useEffect, useState } from 'react';
import { BadgeGroup } from '../../components/badges';
import { Panel, PanelState } from '../../components/panels/Panel';
import { PlanTimelineChart } from '../../components/charts/PlanTimelineChart';
import { apiGet, DEFAULT_SITE_ID } from '../../lib/api';

interface TelemetryPoint {
  at: string;
  soc_kwh: number;
  diesel_on: boolean;
  diesel_kw: number;
  batt_kw: number;
  solar_kw: number;
  load_kw: number;
  source: string;
}

interface TelemetryResponse {
  site_id: string;
  points: TelemetryPoint[];
}

/**
 * Plan vs Actual — PHASE_4 Task 4.2. Shows the current 24h plan (via PlanTimelineChart,
 * built in Phase 1) alongside the measured telemetry for hours that have since executed.
 * The gap between the two IS the forecast error, and it is shown, not smoothed away
 * (ARCHITECTURE.md §3/§4 — the whole rolling-horizon loop exists to correct for it).
 */
export default function PlanVsActualPage() {
  const [state, setState] = useState<PanelState>('loading');
  const [telemetry, setTelemetry] = useState<TelemetryPoint[]>([]);

  const load = () => {
    setState('loading');
    apiGet<TelemetryResponse>('telemetry', { site_id: DEFAULT_SITE_ID, limit: 48 })
      .then((data) => {
        setTelemetry(data.points);
        setState(data.points.length > 0 ? 'ready' : 'empty');
      })
      .catch(() => setState('error'));
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <main className="w-full pt-20 pb-12 px-4 md:px-6 max-w-[1720px] mx-auto flex flex-col gap-6">
      <h1 className="font-sans text-[20px] font-bold text-slate-900">Plan vs Actual</h1>

      <section>
        <PlanTimelineChart siteId={DEFAULT_SITE_ID} />
      </section>

      <Panel
        title="Measured telemetry (last executed hours)"
        state={state}
        emptyMessage="No telemetry recorded yet — the rolling scheduler hasn't ticked for this site"
        onRetry={load}
        badge={<BadgeGroup kinds={['SIMULATED']} />}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-[12px] font-mono">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-100">
                <th className="py-1 pr-4">At</th>
                <th className="py-1 pr-4">SoC (kWh)</th>
                <th className="py-1 pr-4">Solar (kW)</th>
                <th className="py-1 pr-4">Battery (kW)</th>
                <th className="py-1 pr-4">Diesel (kW)</th>
                <th className="py-1 pr-4">Load (kW)</th>
                <th className="py-1">Source</th>
              </tr>
            </thead>
            <tbody>
              {telemetry.map((point) => (
                <tr key={point.at} className="border-b border-slate-50">
                  <td className="py-1 pr-4 text-slate-700">{new Date(point.at).toLocaleString()}</td>
                  <td className="py-1 pr-4">{point.soc_kwh.toFixed(1)}</td>
                  <td className="py-1 pr-4">{point.solar_kw.toFixed(1)}</td>
                  <td className="py-1 pr-4">{point.batt_kw.toFixed(1)}</td>
                  <td className="py-1 pr-4">{point.diesel_kw.toFixed(1)}</td>
                  <td className="py-1 pr-4">{point.load_kw.toFixed(1)}</td>
                  <td className="py-1 text-slate-400">{point.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </main>
  );
}
