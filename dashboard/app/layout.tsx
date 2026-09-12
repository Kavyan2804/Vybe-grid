import './globals.css';
import React from 'react';

export const metadata = {
  title: 'GridPilot Microgrid Operations',
  description: 'Industrial Energy Management & Telemetry',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" class="h-full">
      <body className="h-full antialiased bg-[#F5F7F6] text-[#111827]">{children}</body>
    </html>
  );
}

