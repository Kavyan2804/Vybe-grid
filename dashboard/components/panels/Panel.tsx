import React from 'react';

/**
 * FE_DESIGN.md §9 — every panel implements all five states this component owns.
 * `'ready'` is the sixth, implicit state: nothing wrong, render children plainly. FE_DESIGN's
 * table names only the five exceptions; ready is what's left when none of them apply.
 */
export type PanelState = 'ready' | 'loading' | 'empty' | 'stale' | 'disconnected' | 'error';

export interface PanelProps {
  title: string;
  state: PanelState;
  emptyMessage?: string;
  staleSeconds?: number;
  errorMessage?: string;
  onRetry?: () => void;
  badge?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export const Panel: React.FC<PanelProps> = ({
  title,
  state,
  emptyMessage = 'No data yet',
  staleSeconds,
  errorMessage = 'Something went wrong loading this panel.',
  onRetry,
  badge,
  children,
  className = '',
}) => {
  // Stale/disconnected keep showing the last known value, dimmed — never a spinner, never
  // blanked (FE_DESIGN.md §9: "replacing it with a spinner destroys more information than it
  // conveys"). Ready shows it undimmed. Everything else replaces it with its own state body.
  const showsChildren = state === 'ready' || state === 'stale' || state === 'disconnected';
  const dimmed = state === 'stale' || state === 'disconnected';

  return (
    <div
      data-panel-state={state}
      className={`bg-white border border-slate-200 rounded-xl p-4 flex flex-col gap-2 ${className}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-sans text-[13px] font-semibold text-slate-700">{title}</span>
        <div className="flex items-center gap-2">
          {state === 'stale' && (
            <span className="font-mono text-[10px] font-semibold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
              stale {staleSeconds != null ? `${staleSeconds}s` : ''}
            </span>
          )}
          {state === 'disconnected' && (
            <span className="font-mono text-[10px] font-semibold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
              reconnecting…
            </span>
          )}
          {badge}
        </div>
      </div>

      {state === 'loading' && (
        <div className="animate-pulse flex flex-col gap-2" aria-hidden="true">
          <div className="h-6 w-24 bg-slate-100 rounded" />
          <div className="h-3 w-32 bg-slate-100 rounded" />
        </div>
      )}

      {state === 'empty' && (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[32px] text-slate-300 leading-none">&mdash;</span>
          <span className="font-sans text-[12px] text-slate-400">{emptyMessage}</span>
        </div>
      )}

      {state === 'error' && (
        <div className="flex flex-col gap-2">
          <span className="font-sans text-[12px] text-red-700">{errorMessage}</span>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="self-start font-sans text-[12px] font-semibold text-[#0B6E4F] border border-[#0B6E4F]/30 rounded px-2 py-1 hover:bg-[#0B6E4F]/5"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {showsChildren && <div className={dimmed ? 'text-slate-500' : undefined}>{children}</div>}
    </div>
  );
};
