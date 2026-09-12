'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Badge, BadgeGroup, BadgeKind } from '../components/badges';
import { PlanTimelineChart } from '../components/charts/PlanTimelineChart';
import { ConnectionState, SiteEventStream } from '../lib/sse';

const SITE_ID = 'Dharavi Microgrid';

interface Provenanced {
  value: number;
  badges: BadgeKind[];
}

interface OverviewResponse {
  server_time: string;
  site: { id: string; name: string };
  current: {
    soc_pct: Provenanced;
    diesel_on: boolean;
    solar_kw: Provenanced;
    load_kw: Provenanced;
  } | null;
  today: {
    diesel_hours: Provenanced;
    cost_saved_vs_baseline: Provenanced | null;
    fuel_liters_saved_vs_baseline: Provenanced | null;
  } | null;
  unread_alerts: number;
}

// Shown only until the first real response arrives (or if the backend is unreachable) —
// never a stand-in for "the system has no data yet", which the backend expresses as
// current: null / today: null instead (PRD.md §3: absent beats fabricated).
const MOCK_OVERVIEW: OverviewResponse = {
  server_time: '2026-01-14T09:02:11+05:30',
  site: { id: 'site-001', name: 'Example Village Microgrid' },
  current: {
    soc_pct: { value: 62.4, badges: ['SIMULATED'] },
    diesel_on: false,
    solar_kw: { value: 4.1, badges: ['SIMULATED'] },
    load_kw: { value: 3.2, badges: ['SIMULATED'] },
  },
  today: {
    diesel_hours: { value: 1.5, badges: ['SIMULATED'] },
    cost_saved_vs_baseline: { value: 1240.0, badges: ['SIMULATED', 'BASELINE'] },
    fuel_liters_saved_vs_baseline: { value: 6.2, badges: ['SIMULATED', 'BASELINE'] },
  },
  unread_alerts: 2,
};

const EMPTY_TILE = <span className="font-mono text-[24px] text-slate-300">&mdash;</span>;

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  connecting: 'connecting…',
  open: 'live',
  reconnecting: 'reconnecting…',
  closed: 'disconnected',
};

export default function DashboardOverviewPage() {
  const [overview, setOverview] = useState<OverviewResponse>(MOCK_OVERVIEW);
  const [usingMock, setUsingMock] = useState(true);
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [refreshToken, setRefreshToken] = useState(0);
  const [ticking, setTicking] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadOverview = useCallback(() => {
    fetch(`/api/overview?site_id=${encodeURIComponent(SITE_ID)}`, { cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.statusText)))
      .then((data: OverviewResponse) => {
        setOverview(data);
        setUsingMock(false);
        setLastUpdated(new Date());
      })
      .catch(() => {
        setOverview(MOCK_OVERVIEW);
        setUsingMock(true);
      });
  }, []);

  // Initial load, then one refetch whenever an SSE event or a manual tick bumps refreshToken —
  // this page never polls; every re-fetch has a reason (FE_DESIGN.md §10: "no component fetches
  // on an SSE event" without one).
  useEffect(() => {
    loadOverview();
  }, [loadOverview, refreshToken]);

  // One realtime connection for the page's lifetime. plan.updated / telemetry.updated both just
  // mean "something changed, go re-fetch" — the event payload itself isn't rendered directly.
  useEffect(() => {
    const stream = new SiteEventStream(SITE_ID, {
      onStateChange: setConnection,
      onPlanUpdated: () => setRefreshToken((n) => n + 1),
      onTelemetryUpdated: () => setRefreshToken((n) => n + 1),
    });
    stream.connect();
    return () => stream.close();
  }, []);

  const runTickNow = async () => {
    setTicking(true);
    try {
      const res = await fetch(`/api/tick?site_id=${encodeURIComponent(SITE_ID)}`, { method: 'POST' });
      if (res.ok) {
        // The backend already publishes plan.updated/telemetry.updated on success, which the
        // SSE subscription above will pick up — this direct bump just makes the UI feel
        // instant instead of waiting on the SSE round-trip.
        setRefreshToken((n) => n + 1);
      }
    } finally {
      setTicking(false);
    }
  };

  const { current, today } = overview;

  return (
    <div className="min-h-screen bg-[#F5F7F6] text-[#111827]">
      {/* Header */}
      <header className="fixed top-0 left-0 w-full z-50 bg-white/95 backdrop-blur-md border-b border-slate-200/90">
        <div className="h-16 w-full px-4 lg:px-6 flex items-center justify-between gap-3 max-w-[1720px] mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#0B6E4F] flex items-center justify-center text-white font-bold">
              GP
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-sans text-[17px] font-bold tracking-tight text-slate-900">
                GridPilot
              </span>
              {usingMock && (
                <span className="font-mono text-[10px] font-semibold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                  mock data &mdash; backend unreachable
                </span>
              )}
            </div>
            <div className="h-5 w-px bg-slate-200 hidden sm:block"></div>
            <span className="font-sans text-[13px] font-semibold text-slate-800">
              {overview.site.name} ({overview.site.id})
            </span>
          </div>

          <div className="flex items-center gap-3">
            <span
              data-edge-state={connection}
              className={`font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded border ${
                connection === 'open'
                  ? 'text-[#036B4E] bg-[#036B4E]/10 border-[#036B4E]/25'
                  : 'text-amber-700 bg-amber-50 border-amber-200'
              }`}
            >
              &#9679; {CONNECTION_LABEL[connection]}
            </span>
            {lastUpdated && (
              <span className="font-mono text-[10px] text-slate-400">
                updated {lastUpdated.toLocaleTimeString()}
              </span>
            )}
            <button
              type="button"
              onClick={runTickNow}
              disabled={ticking}
              className="font-sans text-[11px] font-semibold px-2.5 py-1.5 rounded-lg border border-[#0B6E4F]/30 text-[#0B6E4F] hover:bg-[#0B6E4F]/5 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Run the rolling-horizon tick immediately instead of waiting for the hourly schedule"
            >
              {ticking ? 'Running…' : 'Run tick now'}
            </button>
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
              {current ? <BadgeGroup kinds={current.solar_kw.badges} /> : <Badge kind="SIMULATED" />}
            </div>
            <div className="font-mono text-[24px] font-bold text-slate-900 my-1">
              {current ? (
                <>
                  {current.solar_kw.value} <span className="text-[14px] text-slate-500">kW</span>
                </>
              ) : (
                EMPTY_TILE
              )}
            </div>
            <span className="font-sans text-[11px] text-slate-400">Current Instantaneous</span>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-slate-500 font-medium">Battery SoC</span>
              {current ? <BadgeGroup kinds={current.soc_pct.badges} /> : <Badge kind="SIMULATED" />}
            </div>
            <div className="font-mono text-[24px] font-bold text-blue-700 my-1">
              {current ? `${current.soc_pct.value}%` : EMPTY_TILE}
            </div>
            <span className="font-sans text-[11px] text-slate-400">Stored Capacity</span>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-slate-500 font-medium">Site Demand</span>
              {current ? <BadgeGroup kinds={current.load_kw.badges} /> : <Badge kind="SIMULATED" />}
            </div>
            <div className="font-mono text-[24px] font-bold text-slate-900 my-1">
              {current ? (
                <>
                  {current.load_kw.value} <span className="text-[14px] text-slate-500">kW</span>
                </>
              ) : (
                EMPTY_TILE
              )}
            </div>
            <span className="font-sans text-[11px] text-slate-400">Net Active Load</span>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-slate-500 font-medium">Cost Savings</span>
              {today?.cost_saved_vs_baseline ? (
                <BadgeGroup kinds={today.cost_saved_vs_baseline.badges} />
              ) : (
                <Badge kind="BASELINE" />
              )}
            </div>
            <div className="font-mono text-[24px] font-bold text-[#0B6E4F] my-1">
              {today?.cost_saved_vs_baseline ? (
                <>&#8377;{today.cost_saved_vs_baseline.value}</>
              ) : (
                EMPTY_TILE
              )}
            </div>
            <span className="font-sans text-[11px] text-slate-400">vs Diesel Baseline Shadow</span>
          </div>
        </div>

        {/* Task 1.4 Primary Goal: PlanTimelineChart */}
        <section>
          <PlanTimelineChart siteId={overview.site.id} refreshToken={refreshToken} />
        </section>
      </main>
    </div>
  );
}
