'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
  { href: '/', label: 'Overview' },
  { href: '/plan', label: 'Plan vs Actual' },
  { href: '/savings', label: 'Savings Analysis' },
  { href: '/alerts', label: 'Alerts', count: 2 },
];

export function DashboardNav() {
  const pathname = usePathname();

  return (
    <header className="dashboard-nav">
      <div className="dashboard-nav-inner">
        <Link className="dashboard-brand" href="/" aria-label="GridPilot overview">
          <span className="dashboard-brand-mark">⚡</span>
          <span>GridPilot</span>
          <small>v4.8</small>
        </Link>

        <div className="dashboard-site">▦ <span>Site #104 - Bihar Rural</span></div>

        <nav className="dashboard-nav-tabs" aria-label="Dashboard navigation">
          {navItems.map((item) => {
            const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);

            return (
              <Link className={active ? 'active' : ''} href={item.href} key={item.href}>
                {item.label}
                {item.count ? <span className="dashboard-nav-count">{item.count}</span> : null}
              </Link>
            );
          })}
        </nav>

        <div className="dashboard-nav-actions">
          <span className="dashboard-api-status">● API: OFFLINE</span>
          <span className="dashboard-clock">◷ 22:30:19 IST</span>
          <button type="button">↻ Run Tick</button>
        </div>
      </div>
    </header>
  );
}