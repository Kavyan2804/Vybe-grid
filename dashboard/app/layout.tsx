import type { Metadata } from 'next';
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
      <body>{children}</body>
    </html>
  );
}
