'use client';

import React, { useEffect, useState } from 'react';
import { Badge, BadgeGroup, BadgeKind } from '../components/badges';
import { PlanTimelineChart } from '../components/charts/PlanTimelineChart';

interface OverviewResponse {
  server_time: string;
  site: { id: string; name: string };
  current: {
    soc_pct: { value: number; badges: BadgeKind[] };
    diesel_on: { value: boolean; badges: BadgeKind[] };
    solar_kw: { value: number; badges: BadgeKind[] };
    load_kw: { value: number; badges: BadgeKind[] };
  };
  today: {
    diesel_hours: { value: number; badges: BadgeKind[] };
    cost_saved_vs_baseline: { value: number; currency: string; badges: BadgeKind[] };
    fuel_liters_saved_vs_baseline: { value: number; badges: BadgeKind[] };
  };
  unread_alerts: number;
}

const MOCK_OVERVIEW: OverviewResponse = {
  server_time: '2026-01-14T09:02:11+05:30',
  site: { id: 'site-001', name: 'Example Village Microgrid' },
  current: {
    soc_pct: { value: 62.4, badges: ['SIMULATED'] },
    diesel_on: { value: false, badges: ['SIMULATED'] },
    solar_kw: { value: 4.1, badges: ['SIMULATED'] },
    load_kw: { value: 3.2, badges: ['SIMULATED'] },
  },
  today: {
    diesel_hours: { value: 1.5, badges: ['SIMULATED'] },
    cost_saved_vs_baseline: { value: 1240.0, currency: 'INR', badges: ['SIMULATED', 'BASELINE'] },
    fuel_liters_saved_vs_baseline: { value: 6.2, badges: ['SIMULATED', 'BASELINE'] },
  },
  unread_alerts: 2,
};

export default function DashboardOverviewPage() {
  const [overview, setOverview] = useState<OverviewResponse>(MOCK_OVERVIEW);

  useEffect(() => {
    fetch('/api/overview?site_id=site-001')
      .then((res) => (res.ok ? res.json() : Promise.reject(res.statusText)))
      .then((data) => setOverview(data))
      .catch(() => setOverview(MOCK_OVERVIEW));
  }, []);

  return (
    <div className="min-h-screen bg-[#F5F7F6] text-[#111827]">
      {/* Header */}
      <header class="fixed top-0 left-0 w-full z-50 bg-white/95 backdrop-blur-md border-b border-slate-200/90">
        <div className="h-16 w-full px-4 lg:px-6 flex items-center justify-between gap-3 max-w-[1720px] mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#0B6E4F] flex items-center justify-center text-white font-bold">
              GP
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-sans text-[17px] font-bold tracking-tight text-slate-900">
                GridPilot
              </span>
              <span className="font-mono text-[10px] font-semibold text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                v4.8
              </span>
            </div>
            <div className="h-5 w-px bg-slate-200 hidden sm:block"></div>
            <span className="font-sans text-[13px] font-semibold text-slate-800">
              {overview.site.name} ({overview.site.id})
            </span>
          </div>

          <div className="flex items-center gap-2">
            <BadgeGroup kinds={['LIVE', 'FORECAST', 'SIMULATED', 'BASELINE']} />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="w-full pt-20 pb-12 px-4 md:px-6 max-w-[1720px] mx-auto flex flex-col gap-6">
        {/* KPI Tiles with Explicit Badging */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-slate-500 font-medium">Solar Power</span>
              <BadgeGroup kinds={overview.current.solar_kw.badges} />
            </div>
            <div className="font-mono text-[24px] font-bold text-slate-900 my-1">
              {overview.current.solar_kw.value} <span class="text-[14px] text-slate-500">kW</span>
            </div>
            <span className="font-sans text-[11px] text-slate-400">Current Instantaneous</span>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-slate-500 font-medium">Battery SoC</span>
              <BadgeGroup kinds={overview.current.soc_pct.badges} />
            </div>
            <div className="font-mono text-[24px] font-bold text-blue-700 my-1">
              {overview.current.soc_pct.value}%
            </div>
            <span className="font-sans text-[11px] text-slate-400">Stored Capacity</span>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-slate-500 font-medium">Site Demand</span>
              <BadgeGroup kinds={overview.current.load_kw.badges} />
            </div>
            <div className="font-mono text-[24px] font-bold text-slate-900 my-1">
              {overview.current.load_kw.value} <span className="text-[14px] text-slate-500">kW</span>
            </div>
            <span className="font-sans text-[11px] text-slate-400">Net Active Load</span>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-slate-500 font-medium">Cost Savings</span>
              <BadgeGroup kinds={overview.today.cost_saved_vs_baseline.badges} />
            </div>
            <div className="font-mono text-[24px] font-bold text-[#0B6E4F] my-1">
              ₹{overview.today.cost_saved_vs_baseline.value}
            </div>
            <span className="font-sans text-[11px] text-slate-400">vs Diesel Baseline Shadow</span>
          </div>
        </div>

        {/* Task 1.4 Primary Goal: PlanTimelineChart */}
        <section>
          <PlanTimelineChart siteId={overview.site.id} />
        </section>
      </main>
    </div>
  );
}

