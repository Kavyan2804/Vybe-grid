import type { HTMLAttributes } from 'react';

export type BadgeKind = 'LIVE' | 'FORECAST' | 'SIMULATED' | 'BASELINE';
export type BadgeTone = 'live' | 'forecast' | 'simulated' | 'baseline' | 'danger' | 'neutral';

const kindToTone: Record<BadgeKind, BadgeTone> = {
  LIVE: 'live',
  FORECAST: 'forecast',
  SIMULATED: 'simulated',
  BASELINE: 'baseline',
};

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
  kind?: BadgeKind;
};

export function Badge({ tone, kind, className = '', children, ...props }: BadgeProps) {
  const resolvedTone = tone ?? (kind ? kindToTone[kind] : 'neutral');
  const label = children ?? kind;
  return (
    <span className={`badge-provenance ${toneClasses[resolvedTone]} ${className}`.trim()} {...props}>
      {label}
    </span>
  );
}

type BadgeGroupProps = {
  kinds: BadgeKind[];
  className?: string;
};

export function BadgeGroup({ kinds, className = '' }: BadgeGroupProps) {
  return (
    <span className={`badge-group ${className}`.trim()}>
      {kinds.map((kind) => (
        <Badge key={kind} kind={kind} />
      ))}
    </span>
  );
}
