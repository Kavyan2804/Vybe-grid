import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'GridPilot Dashboard',
  description: 'Microgrid telemetry and dispatch operations dashboard',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <header className="app-header">
          <Link href="/" className="brand">
            GridPilot
          </Link>
          <nav className="app-nav">
            <Link href="/">Overview</Link>
            <Link href="/plan">Plan</Link>
            <Link href="/savings">Savings</Link>
            <Link href="/alerts">Alerts</Link>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
