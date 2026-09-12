'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

const navItems = [
  { href: '/', label: 'Overview' },
  { href: '/plan', label: 'Plan vs Actual' },
  { href: '/savings', label: 'Savings Analysis' },
  { href: '/alerts', label: 'Alerts' },
];

export function DashboardNav() {
  const pathname = usePathname();
  const [clock, setClock] = useState('');
  const [apiOnline, setApiOnline] = useState(false);
  const siteId = 'Dharavi Microgrid';
  let pendingTicks = 0;
  let tickProcessing = false;

  useEffect(() => {
    const updateClock = () => {
      setClock(
        new Intl.DateTimeFormat('en-GB', {
          timeZone: 'Asia/Kolkata',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        }).format(new Date())
      );
    };
    updateClock();
    const timer = window.setInterval(updateClock, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let mounted = true;

    const checkApi = async () => {
      try {
        const response = await fetch('/api/health', { cache: 'no-store' });
        if (mounted) setApiOnline(response.ok);
      } catch {
        if (mounted) setApiOnline(false);
      }
    };

    checkApi();
    const timer = window.setInterval(checkApi, 10000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  async function runTick() {
    const button = document.querySelector<HTMLButtonElement>('.dashboard-nav-actions button');
    pendingTicks += 1;
    if (tickProcessing) return;
    tickProcessing = true;
    while (pendingTicks > 0) {
      pendingTicks -= 1;
      if (button) button.setAttribute('aria-busy', 'true');
      try {
        const response = await fetch(`/api/tick?site_id=${encodeURIComponent(siteId)}`, {
          method: 'POST',
          cache: 'no-store',
        });
        if (!response.ok) {
          throw new Error(`Tick request failed with status ${response.status}`);
        }
        const dashboardFrame = document.querySelector<HTMLIFrameElement>('iframe[title="GridPilot Microgrid Telemetry Operations"]');
        dashboardFrame?.contentWindow?.postMessage(
          { type: 'gridpilot:refresh' },
          window.location.origin
        );
      } catch (error) {
        console.error('GridPilot tick failed:', error);
      } finally {
        if (button) button.removeAttribute('aria-busy');
      }
    }
    tickProcessing = false;
  }

  return (
    <header className="dashboard-nav">
      <div className="dashboard-nav-inner">
        <Link className="dashboard-brand" href="/" aria-label="GridPilot overview">
          <span className="dashboard-brand-mark">⚡</span>
          <span>GridPilot</span>
          <small>v4.8</small>
        </Link>

        <div className="dashboard-site">▦ <span>Dharavi Microgrid</span></div>

        <nav className="dashboard-nav-tabs" aria-label="Dashboard navigation">
          {navItems.map((item) => {
            const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);

            return (
            <Link className={active ? 'active' : ''} href={item.href} key={item.href}>
              {item.label}
            </Link>
            );
          })}
        </nav>

        <div className="dashboard-nav-actions">
          <span className="dashboard-api-status">
            ● API: {apiOnline ? 'ONLINE' : 'OFFLINE'}
          </span>
          <span className="dashboard-clock">◷ {clock || '--:--:--'} IST</span>
          <button type="button" onClick={runTick}>↻ Run Tick</button>
        </div>
      </div>
    </header>
  );
}