// Browser requests use the Next.js BFF so they work in both local and containerized
// deployments. Server components call the backend directly because Node's fetch does not
// accept a relative URL.
export const API_BASE =
  process.env.NEXT_PUBLIC_GRIDPILOT_API_BASE ??
  (typeof window === 'undefined'
    ? `${process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'}/api`
    : '/api');
export const DEFAULT_SITE_ID = process.env.NEXT_PUBLIC_GRIDPILOT_SITE_ID ?? 'Dharavi Microgrid';

export type ApiValue = {
  value: number;
  unit?: string;
  source?: string;
  badges?: string[];
};

export type OverviewResponse = {
  server_time?: string;
  site?: { id?: string; name?: string };
  current?: {
    solar_kw: ApiValue;
    load_kw: ApiValue;
    soc_pct: ApiValue;
    diesel_on?: boolean;
  } | null;
  today?: {
    cost_saved_vs_baseline?: ApiValue | null;
    fuel_liters_saved_vs_baseline?: ApiValue | null;
    diesel_hours?: ApiValue;
  } | null;
  unread_alerts?: number;
};

export type PlanSeriesItem = {
  hour: number;
  diesel_on?: boolean;
  solar_used_kw?: number;
  batt_charge_kw?: number;
  batt_discharge_kw?: number;
  diesel_kw?: number;
  soc_kwh?: number;
  solar_curtailed_kw?: number;
  unmet_flex_kw?: number;
  executed?: boolean;
  badges?: string[];
};

export type LatestPlanResponse = {
  plan_id?: string;
  site_id?: string;
  tick_at?: string;
  starting_soc_kwh?: number;
  solver_status?: string;
  solve_ms?: number;
  objective_cost?: number;
  series?: PlanSeriesItem[];
};

export type SavingsMetrics = {
  diesel_kwh: number;
  fuel_litres: number;
  cost: number;
  co2_kg: number;
  diesel_hours: number;
};

export type SavingsComparison = {
  plan_id: number | string;
  site_id: string;
  hours: unknown[];
};

export type SavingsResponse = {
  comparison: SavingsComparison;
  optimized: SavingsMetrics;
  baseline: SavingsMetrics;
  saved?: {
    cost?: number;
    fuel_litres?: number;
    diesel_hours?: number;
    co2_kg?: number;
  };
};

export async function gridpilotFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`GridPilot API request failed: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export function siteQuery(siteId = DEFAULT_SITE_ID) {
  return `site_id=${encodeURIComponent(siteId)}`;
}
