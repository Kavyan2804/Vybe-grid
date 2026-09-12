import React from 'react';
import { Badge, BadgeKind } from './Badge';

export interface BadgeGroupProps {
  kinds: BadgeKind[];
  className?: string;
}

export const BadgeGroup: React.FC<BadgeGroupProps> = ({ kinds, className = '' }) => {
  if (!kinds || kinds.length === 0) {
    return <span className="font-mono text-[10px] text-slate-400">—</span>;
  }

  return (
    <div className={`inline-flex items-center gap-1 flex-wrap ${className}`}>
      {kinds.map((kind, idx) => (
        <Badge key={`${kind}-${idx}`} kind={kind} />
      ))}
    </div>
  );
};

