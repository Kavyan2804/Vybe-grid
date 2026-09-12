import type { HTMLAttributes } from 'react';

export type BadgeTone = 'live' | 'forecast' | 'simulated' | 'baseline' | 'danger' | 'neutral';

const toneClasses: Record<BadgeTone, string> = {
  live: 'badge-live',
  forecast: 'badge-forecast',
  simulated: 'badge-simulated',
  baseline: 'badge-baseline',
  danger: 'badge-danger',
  neutral: 'badge-neutral',
};

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone;
};

export function Badge({ tone = 'neutral', className = '', children, ...props }: BadgeProps) {
  return (
    <span className={`badge-provenance ${toneClasses[tone]} ${className}`.trim()} {...props}>
      {children}
    </span>
  );
}
