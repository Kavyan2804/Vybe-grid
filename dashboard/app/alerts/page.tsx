'use client';

import React, { useEffect, useState } from 'react';
import { Badge, BadgeKind } from '../../components/badges';
import { Panel, PanelState } from '../../components/panels/Panel';
import { apiGet, apiPost, DEFAULT_SITE_ID } from '../../lib/api';

type AlertStatus = 'active' | 'acknowledged' | 'resolved';

interface AlertItem {
  id: string;
  site_id: string;
  type: string;
  title: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
  status: AlertStatus;
  created_at: string;
  raised_at: string | null;
  received_at: string | null;
  provenance: BadgeKind[];
}

interface AlertListResponse {
  total: number;
  items: AlertItem[];
}

const TABS: { label: string; value: AlertStatus | 'all' }[] = [
  { label: 'Open', value: 'active' },
  { label: 'Acknowledged', value: 'acknowledged' },
  { label: 'Resolved', value: 'resolved' },
];

function gapSeconds(a: AlertItem): number | null {
  if (!a.raised_at || !a.received_at) return null;
  return Math.round((new Date(a.received_at).getTime() - new Date(a.raised_at).getTime()) / 1000);
}

/**
 * Alert centre — PHASE_4 Task 4.4. Both clocks always shown (raised_at from whatever raised
 * it, received_at from the server); a gap over a few seconds is highlighted rather than
 * hidden — that gap is the cable-pull's payoff, not a bug (FE_DESIGN.md §7).
 */
export default function AlertsPage() {
  const [tab, setTab] = useState<AlertStatus | 'all'>('active');
  const [state, setState] = useState<PanelState>('loading');
  const [alerts, setAlerts] = useState<AlertItem[]>([]);

  const load = () => {
    setState('loading');
    apiGet<AlertListResponse>('alerts', tab === 'all' ? { site_id: DEFAULT_SITE_ID } : { site_id: DEFAULT_SITE_ID, status: tab })
      .then((res) => {
        setAlerts(res.items);
        setState(res.items.length > 0 ? 'ready' : 'empty');
      })
      .catch(() => setState('error'));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const act = (id: string, action: 'acknowledge' | 'resolve') => {
    apiPost(`alerts/${id}/${action}`, {}).then(load).catch(load);
  };

  return (
    <main className="w-full pt-20 pb-12 px-4 md:px-6 max-w-[1720px] mx-auto flex flex-col gap-4">
      <h1 className="font-sans text-[20px] font-bold text-slate-900">Alerts</h1>

      <div className="flex items-center gap-2">
        {TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => setTab(t.value)}
            className={`font-sans text-[12px] font-semibold px-3 py-1.5 rounded-full border ${
              tab === t.value
                ? 'bg-[#0B6E4F] text-white border-[#0B6E4F]'
                : 'bg-white text-slate-600 border-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <Panel
        title={`${TABS.find((t) => t.value === tab)?.label ?? 'Open'} alerts`}
        state={state}
        emptyMessage="Nothing here — quiet is good"
        onRetry={load}
      >
        <div className="flex flex-col gap-3">
          {alerts.map((alert) => {
            const gap = gapSeconds(alert);
            const highlighted = gap !== null && gap > 2;
            return (
              <div key={alert.id} className="border border-slate-200 rounded-lg p-3 flex flex-col gap-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[11px] text-slate-400">{alert.type}</span>
                      {alert.provenance.map((b) => (
                        <Badge key={b} kind={b} />
                      ))}
                    </div>
                    <div className="font-sans text-[14px] font-semibold text-slate-900 mt-1">{alert.title}</div>
                    <div className="font-sans text-[12px] text-slate-500">{alert.message}</div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    {alert.status === 'active' && (
                      <button
                        onClick={() => act(alert.id, 'acknowledge')}
                        className="font-sans text-[11px] font-semibold px-2 py-1 rounded border border-slate-200 text-slate-600 hover:bg-slate-50"
                      >
                        Acknowledge
                      </button>
                    )}
                    {alert.status !== 'resolved' && (
                      <button
                        onClick={() => act(alert.id, 'resolve')}
                        className="font-sans text-[11px] font-semibold px-2 py-1 rounded border border-[#0B6E4F]/30 text-[#0B6E4F] hover:bg-[#0B6E4F]/5"
                      >
                        Resolve
                      </button>
                    )}
                  </div>
                </div>
                <div
                  className={`flex gap-4 font-mono text-[11px] ${highlighted ? 'text-amber-700' : 'text-slate-400'}`}
                  title={highlighted ? 'buffered on the edge during a network interruption; the raised timestamp is preserved' : undefined}
                >
                  <span>raised {alert.raised_at ? new Date(alert.raised_at).toLocaleTimeString() : '—'}</span>
                  <span>received {alert.received_at ? new Date(alert.received_at).toLocaleTimeString() : '—'}</span>
                  {highlighted && <span>gap {gap}s</span>}
                </div>
              </div>
            );
          })}
        </div>
      </Panel>
    </main>
  );
}
