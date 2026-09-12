import React from 'react';

export type BadgeKind = 'LIVE' | 'FORECAST' | 'SIMULATED' | 'BASELINE';

export interface BadgeProps {
  kind: BadgeKind;
  className?: string;
}

const BADGE_STYLES: Record<BadgeKind, { bg: string; text: string; border: string }> = {
  LIVE: {
    bg: 'bg-[#036B4E]/12',
    text: 'text-[#036B4E]',
    border: 'border-[#036B4E]/25',
  },
  FORECAST: {
    bg: 'bg-[#1D4ED8]/12',
    text: 'text-[#1D4ED8]',
    border: 'border-[#1D4ED8]/25',
  },
  SIMULATED: {
    bg: 'bg-[#6D28D9]/12',
    text: 'text-[#6D28D9]',
    border: 'border-[#6D28D9]/25',
  },
  BASELINE: {
    bg: 'bg-[#92400E]/12',
    text: 'text-[#92400E]',
    border: 'border-[#92400E]/25',
  },
};

export const Badge: React.FC<BadgeProps> = ({ kind, className = '' }) => {
  const style = BADGE_STYLES[kind];

  if (!style) {
    console.warn(`[Badge] Unknown kind "${kind}" provided. Falling back to default.`);
    return <span className="font-mono text-[10px] text-slate-400">—</span>;
  }

  return (
    <span
      data-badge-kind={kind}
      className={`inline-flex items-center justify-center font-mono text-[10px] font-bold uppercase tracking-[0.05em] whitespace-nowrap px-1.5 py-0.5 rounded border leading-none select-none h-5 shrink-0 ${style.bg} ${style.text} ${style.border} ${className}`}
    >
      {kind}
    </span>
  );
};

