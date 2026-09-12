import type { ReactNode } from 'react';

export type PanelState = 'loading' | 'empty' | 'stale' | 'disconnected' | 'error' | 'ready';

type PanelProps = {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  state?: PanelState;
  message?: string;
};

export function Panel({
  title,
  eyebrow,
  action,
  children,
  className = '',
  state = 'ready',
  message,
}: PanelProps) {
  const showBody = state === 'ready' || state === 'stale';
  return (
    <section className={`instrument-card panel panel-${state} ${className}`.trim()} data-state={state}>
      <div className="panel-header">
        <div>
          {eyebrow ? <p className="panel-eyebrow">{eyebrow}</p> : null}
          <h2>{title}</h2>
        </div>
        <div className="panel-action">
          {state === 'stale' ? <span className="stale-chip">stale</span> : null}
          {state === 'disconnected' ? <span className="stale-chip">disconnected</span> : null}
          {action}
        </div>
      </div>
      <div className="panel-body">
        {showBody ? children : null}
        {state === 'loading' ? <p className="muted">{message ?? 'Loading…'}</p> : null}
        {state === 'empty' ? <p className="muted">{message ?? 'No data yet.'}</p> : null}
        {state === 'error' ? <p className="muted">{message ?? 'Something went wrong.'}</p> : null}
        {state === 'disconnected' ? (
          <p className="muted">{message ?? 'Reconnecting… last values kept when available.'}</p>
        ) : null}
      </div>
    </section>
  );
}
