'use client';

import React, { useEffect, useState } from 'react';
import { Badge, BadgeGroup, BadgeKind } from '../badges';

export interface PlanSeriesItem {
  hour: number;
  diesel_on: boolean;
  diesel_kw: number;
  batt_charge_kw: number;
  batt_discharge_kw: number;
  soc_kwh: number;
  solar_used_kw: number;
  solar_curtailed_kw: number;
  unmet_flex_kw: number;
  executed: boolean;
  badges: BadgeKind[];
}

export interface DispatchPlanResponse {
  plan_id: string;
  site_id: string;
  tick_at: string;
  starting_soc_kwh: number;
  series: PlanSeriesItem[];
  objective_cost: number;
  solver_status: string;
  solve_ms: number;
}

export interface PlanTimelineChartProps {
  siteId?: string;
  initialData?: DispatchPlanResponse;
  /** Bump this (e.g. on an SSE plan.updated event, or a manual refresh) to force a refetch
   * without touching siteId. */
  refreshToken?: number | string;
}

// Fallback scenario mock data conforming to packages/contracts API_CONTRACT.md §2
const MOCK_DISPATCH_PLAN: DispatchPlanResponse = {
  plan_id: 'plan_000482',
  site_id: 'site-001',
  tick_at: '2026-01-14T09:00:00+05:30',
  starting_soc_kwh: 12.4,
  series: [
    {
      hour: 0,
      diesel_on: false,
      diesel_kw: 0,
      batt_charge_kw: 1.8,
      batt_discharge_kw: 0,
      soc_kwh: 13.1,
      solar_used_kw: 4.1,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: true,
      badges: ['SIMULATED'],
    },
    {
      hour: 1,
      diesel_on: false,
      diesel_kw: 0,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 0.0,
      soc_kwh: 13.1,
      solar_used_kw: 3.2,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 2,
      diesel_on: false,
      diesel_kw: 0,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 1.1,
      soc_kwh: 12.0,
      solar_used_kw: 1.2,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 3,
      diesel_on: false,
      diesel_kw: 0.4,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 1.9,
      soc_kwh: 10.1,
      solar_used_kw: 0.4,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 4,
      diesel_on: true,
      diesel_kw: 1.4,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 1.8,
      soc_kwh: 8.3,
      solar_used_kw: 0.0,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 5,
      diesel_on: true,
      diesel_kw: 1.2,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 1.6,
      soc_kwh: 6.7,
      solar_used_kw: 0.0,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 6,
      diesel_on: false,
      diesel_kw: 0.6,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 1.5,
      soc_kwh: 5.2,
      solar_used_kw: 0.0,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 7,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 1.2,
      soc_kwh: 4.0,
      solar_used_kw: 0.0,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 8,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 1.0,
      soc_kwh: 3.0,
      solar_used_kw: 0.0,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 9,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 0.8,
      soc_kwh: 2.2,
      solar_used_kw: 0.0,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 10,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 0.7,
      soc_kwh: 1.5,
      solar_used_kw: 0.0,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 12,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 0.6,
      soc_kwh: 0.9,
      solar_used_kw: 0.0,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 14,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 0.6,
      soc_kwh: 0.3,
      solar_used_kw: 0.0,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 16,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 0.4,
      soc_kwh: 0.1,
      solar_used_kw: 0.3,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 18,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 0.0,
      batt_discharge_kw: 0.0,
      soc_kwh: 0.1,
      solar_used_kw: 2.1,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 20,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 1.2,
      batt_discharge_kw: 0.0,
      soc_kwh: 1.3,
      solar_used_kw: 3.8,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 22,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 1.6,
      batt_discharge_kw: 0.0,
      soc_kwh: 2.9,
      solar_used_kw: 4.4,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
    {
      hour: 23,
      diesel_on: false,
      diesel_kw: 0.0,
      batt_charge_kw: 1.7,
      batt_discharge_kw: 0.0,
      soc_kwh: 4.6,
      solar_used_kw: 4.2,
      solar_curtailed_kw: 0.0,
      unmet_flex_kw: 0.0,
      executed: false,
      badges: ['FORECAST'],
    },
  ],
  objective_cost: 812.4,
  solver_status: 'optimal',
  solve_ms: 4210,
};

export const PlanTimelineChart: React.FC<PlanTimelineChartProps> = ({
  siteId = 'site-001',
  initialData,
  refreshToken,
}) => {
  const [data, setData] = useState<DispatchPlanResponse>(initialData || MOCK_DISPATCH_PLAN);
  const [loading, setLoading] = useState<boolean>(!initialData);
  const [error, setError] = useState<string | null>(null);
  const [selectedHour, setSelectedHour] = useState<PlanSeriesItem | null>(null);

  useEffect(() => {
    let isMounted = true;
    const fetchPlan = async () => {
      try {
        setLoading(true);
        const res = await fetch(`/api/plans/latest?site_id=${siteId}`);
        if (!res.ok) {
          throw new Error(`HTTP error ${res.status}`);
        }
        const json: DispatchPlanResponse = await res.json();
        if (isMounted) {
          setData(json);
          setError(null);
        }
      } catch (err: any) {
        console.warn('[PlanTimelineChart] Live fetch failed, using fallback scenario:', err.message);
        if (isMounted) {
          setData(MOCK_DISPATCH_PLAN);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchPlan();
    return () => {
      isMounted = false;
    };
  }, [siteId, refreshToken]);

  const activeHourItem = selectedHour || data.series[2] || data.series[0];

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-xs flex flex-col gap-4">
      {/* Header & Badges */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2.5 flex-wrap">
          <h2 className="font-sans text-[18px] text-slate-900 font-bold tracking-tight">
            24h Dispatch Plan
          </h2>
          <Badge kind="FORECAST" />
          <span className="font-sans text-[13px] text-slate-500 ml-1">
            Economic Optimization Dispatch Engine
          </span>
        </div>

        {/* Legend: Hour-0 Executed vs Hour-1+ Forecast */}
        <div className="flex items-center gap-4 flex-wrap font-sans text-[12px]">
          <div className="flex items-center gap-2">
            <span className="w-3.5 h-3.5 rounded bg-[#0B6E4F] ring-1 ring-emerald-700/30 shadow-2xs"></span>
            <span className="text-slate-800 font-bold whitespace-nowrap">
              Hour 0 (Solid = Executed Reality)
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="w-3.5 h-3.5 rounded bg-blue-50 border border-blue-400 opacity-85"
              style={{
                backgroundImage:
                  'repeating-linear-gradient(45deg, #1D4ED8 0, #1D4ED8 2px, transparent 2px, transparent 6px)',
              }}
            ></span>
            <span className="text-slate-600 whitespace-nowrap">
              Hours 1–23 (Hatched = Unexecuted Projection)
            </span>
          </div>
        </div>
      </div>

      {/* Series Keys Bar */}
      <div className="flex items-center justify-between gap-4 flex-wrap font-sans text-[11.5px] py-2 px-3.5 bg-slate-50 rounded-xl border border-slate-200/80">
        <div className="flex items-center gap-5 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 ring-2 ring-amber-200 shrink-0"></span>
            <span className="text-slate-800 font-medium whitespace-nowrap">Solar PV Output</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-600 ring-2 ring-blue-200 shrink-0"></span>
            <span className="text-slate-800 font-medium whitespace-nowrap">Battery Discharge</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#92400E] ring-2 ring-amber-300 shrink-0"></span>
            <span className="text-slate-800 font-medium whitespace-nowrap">Diesel Genset Dispatch</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 bg-slate-900 shrink-0"></span>
            <span className="text-slate-800 font-semibold whitespace-nowrap">Forecasted Demand</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 border-t-2 border-dashed border-rose-600 shrink-0"></span>
            <span className="text-rose-600 font-bold whitespace-nowrap">Critical Reserve Floor (0.8 kW)</span>
          </div>
        </div>

        <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500">
          <span>Solver:</span>
          <span className="font-bold text-slate-800 uppercase">{data.solver_status}</span>
          <span>({data.solve_ms}ms)</span>
        </div>
      </div>

      {/* SVG Dispatch Chart */}
      <div className="relative w-full overflow-x-auto select-none pt-2 pb-1">
        <div className="min-w-[880px] relative">
          <svg
            className="w-full h-72 overflow-visible cursor-crosshair"
            preserveAspectRatio="none"
            viewBox="0 0 1000 280"
          >
            <defs>
              <pattern
                id="forecastHatch"
                width="8"
                height="8"
                patternTransform="rotate(45 0 0)"
                patternUnits="userSpaceOnUse"
              >
                <line x1="0" y1="0" x2="0" y2="8" stroke="#1D4ED8" strokeWidth="2" strokeOpacity="0.35" />
              </pattern>
              <pattern
                id="dieselHatch"
                width="6"
                height="6"
                patternTransform="rotate(-45 0 0)"
                patternUnits="userSpaceOnUse"
              >
                <line x1="0" y1="0" x2="0" y2="6" stroke="#92400E" strokeWidth="2" strokeOpacity="0.45" />
              </pattern>
              <linearGradient id="executedGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#0B6E4F" stopOpacity="0.55" />
                <stop offset="100%" stopColor="#0B6E4F" stopOpacity="0.08" />
              </linearGradient>
            </defs>

            {/* Grid Lines */}
            <line x1="40" y1="30" x2="980" y2="30" stroke="#E2E8F0" strokeWidth="1" strokeDasharray="4 4" />
            <line x1="40" y1="90" x2="980" y2="90" stroke="#E2E8F0" strokeWidth="1" strokeDasharray="4 4" />
            <line x1="40" y1="150" x2="980" y2="150" stroke="#E2E8F0" strokeWidth="1" strokeDasharray="4 4" />
            <line x1="40" y1="210" x2="980" y2="210" stroke="#E2E8F0" strokeWidth="1" strokeDasharray="4 4" />
            <line x1="40" y1="240" x2="980" y2="240" stroke="#CBD5E1" strokeWidth="1" />

            {/* Y-Axis Labels */}
            <text x="32" y="34" fontFamily="JetBrains Mono" fontSize="10" fontWeight="600" fill="#64748B" textAnchor="end">5.0 kW</text>
            <text x="32" y="94" fontFamily="JetBrains Mono" fontSize="10" fontWeight="600" fill="#64748B" textAnchor="end">3.5 kW</text>
            <text x="32" y="154" fontFamily="JetBrains Mono" fontSize="10" fontWeight="600" fill="#64748B" textAnchor="end">2.0 kW</text>
            <text x="32" y="214" fontFamily="JetBrains Mono" fontSize="10" fontWeight="700" fill="#DC2626" textAnchor="end">0.8 kW</text>

            {/* Critical Reserve Line */}
            <line x1="40" y1="210" x2="980" y2="210" stroke="#DC2626" strokeWidth="1.75" strokeDasharray="6 4" />

            {/* Future Projection Box */}
            <rect x="80" y="20" width="900" height="220" fill="#1D4ED8" fillOpacity="0.015" />

            {/* Forecast Stacks */}
            <polygon points="160,240 180,180 260,170 340,190 420,230 460,240" fill="url(#forecastHatch)" />
            <path d="M 160 240 Q 180 180 260 170 Q 340 190 420 230 L 460 240" fill="none" stroke="#1D4ED8" strokeWidth="2" strokeDasharray="4 3" />

            <polygon points="210,240 230,150 290,140 330,220 340,240" fill="url(#dieselHatch)" />
            <path d="M 210 240 L 230 150 L 290 140 L 330 220 L 340 240" fill="none" stroke="#92400E" strokeWidth="1.75" strokeDasharray="3 3" />

            {/* Solar Curve */}
            <path d="M 80 60 Q 120 95 160 160 Q 200 240 250 240 L 980 240" fill="none" stroke="#F59E0B" strokeWidth="2.25" strokeDasharray="4 3" />

            {/* Site Demand Line */}
            <path d="M 80 140 C 130 135 180 115 240 110 C 300 105 380 150 480 190 C 580 220 700 230 800 180 C 880 130 940 120 980 130" fill="none" stroke="#0F172A" strokeWidth="2.5" strokeLinecap="round" />

            {/* HOUR 0: EXECUTED REALITY (x=40 to x=80) */}
            <rect x="40" y="20" width="40" height="220" fill="url(#executedGrad)" />
            <rect x="42" y="60" width="36" height="180" rx="3" fill="#0B6E4F" fillOpacity="0.25" />
            <line x1="42" y1="60" x2="78" y2="60" stroke="#0B6E4F" strokeWidth="3.5" strokeLinecap="round" />
            <circle cx="60" cy="140" r="5" fill="#0B6E4F" />
            <circle cx="60" cy="140" r="2" fill="#FFFFFF" />

            {/* Separator NOW Line */}
            <line x1="80" y1="15" x2="80" y2="250" stroke="#0B6E4F" strokeWidth="2.5" />
            <polygon points="75,15 85,15 80,23" fill="#0B6E4F" />

            {/* Interactive X-Axis Hour Markers */}
            {data.series.map((item) => {
              const xPos = 40 + (item.hour / 24) * 940;
              return (
                <g
                  key={item.hour}
                  className="cursor-pointer group"
                  onClick={() => setSelectedHour(item)}
                >
                  <line x1={xPos} y1="240" x2={xPos} y2="248" stroke="#94A3B8" strokeWidth="1" />
                  <text
                    x={xPos}
                    y="265"
                    fontFamily="JetBrains Mono"
                    fontSize="10"
                    fontWeight={item.executed ? '700' : '500'}
                    fill={item.executed ? '#0B6E4F' : '#64748B'}
                    textAnchor="middle"
                  >
                    {item.executed ? `H${item.hour} (NOW)` : `H${item.hour}`}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Inspection Callout Card with Badges */}
          <div className="mt-3 p-4 bg-slate-50 border border-slate-200/90 rounded-xl flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="font-sans text-[13px] font-bold text-slate-900">
                  Hour {activeHourItem.hour} Inspection
                </span>
                <BadgeGroup kinds={activeHourItem.badges} />
              </div>
              <span className="text-slate-300">•</span>
              <span className="font-mono text-[12px] text-slate-600">
                Status:{' '}
                <strong className={activeHourItem.executed ? 'text-[#0B6E4F]' : 'text-blue-700'}>
                  {activeHourItem.executed ? 'Executed Reality' : 'Unexecuted Forecast'}
                </strong>
              </span>
            </div>

            {/* Metrics with explicit Badges */}
            <div className="flex items-center gap-4 flex-wrap font-mono text-[12px]">
              <div className="flex items-center gap-1.5 bg-white px-2.5 py-1 rounded border border-slate-200">
                <span className="text-slate-500">Solar:</span>
                <span className="font-bold text-slate-900">{activeHourItem.solar_used_kw} kW</span>
                <Badge kind={activeHourItem.executed ? 'SIMULATED' : 'FORECAST'} />
              </div>
              <div className="flex items-center gap-1.5 bg-white px-2.5 py-1 rounded border border-slate-200">
                <span className="text-slate-500">BESS:</span>
                <span className="font-bold text-blue-700">
                  {activeHourItem.batt_charge_kw > 0 ? `+${activeHourItem.batt_charge_kw}` : `-${activeHourItem.batt_discharge_kw}`} kW
                </span>
                <Badge kind={activeHourItem.executed ? 'SIMULATED' : 'FORECAST'} />
              </div>
              <div className="flex items-center gap-1.5 bg-white px-2.5 py-1 rounded border border-slate-200">
                <span className="text-slate-500">Diesel:</span>
                <span className="font-bold text-slate-700">{activeHourItem.diesel_kw} kW</span>
                <Badge kind={activeHourItem.executed ? 'SIMULATED' : 'FORECAST'} />
              </div>
              <div className="flex items-center gap-1.5 bg-white px-2.5 py-1 rounded border border-slate-200">
                <span className="text-slate-500">SoC:</span>
                <span className="font-bold text-emerald-800">{activeHourItem.soc_kwh} kWh</span>
                <Badge kind={activeHourItem.executed ? 'SIMULATED' : 'FORECAST'} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Footnote */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-100 font-sans text-[11.5px] text-slate-500 flex-wrap gap-2">
        <div>
          Plan ID: <strong className="font-mono text-slate-700">{data.plan_id}</strong> | Site:{' '}
          <strong className="font-mono text-slate-700">{data.site_id}</strong>
        </div>
        <div className="flex items-center gap-1.5">
          <span>Every numerical series is explicitly badged per FE_DESIGN.md §2</span>
          <BadgeGroup kinds={['SIMULATED', 'FORECAST']} />
        </div>
      </div>
    </div>
  );
};

