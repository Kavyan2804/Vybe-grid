import type { ReactNode } from 'react';

type PanelProps = {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Panel({ title, eyebrow, action, children, className = '' }: PanelProps) {
  return (
    <section className={`instrument-card panel ${className}`.trim()}>
      <div className="panel-header">
        <div>
          {eyebrow ? <p className="panel-eyebrow">{eyebrow}</p> : null}
          <h2>{title}</h2>
        </div>
        {action ? <div className="panel-action">{action}</div> : null}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}
