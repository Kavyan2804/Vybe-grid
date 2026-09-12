/**
 * Native EventSource client — FE_DESIGN.md §8/§10. No library, one connection per site,
 * reconnect backoff 1s -> 2s -> 5s -> 10s (capped), resync via a plain fetch on reconnect.
 *
 * Connects directly to the backend's origin rather than through the BFF: `/api/events/stream`
 * is a long-lived stream, and proxying SSE through a Next.js route handler means manually
 * re-implementing a readable-stream passthrough for one endpoint — not worth it for a
 * same-origin-CORS-already-open backend. Every other request still goes through the BFF
 * (`lib/api.ts`); this is the one deliberate exception, not a precedent.
 */

export type ConnectionState = 'connecting' | 'open' | 'reconnecting' | 'closed';

export interface SseHandlers {
  onPlanUpdated?: (data: unknown) => void;
  onTelemetryUpdated?: (data: unknown) => void;
  onAlertCreated?: (data: unknown) => void;
  onStateChange?: (state: ConnectionState) => void;
}

const BACKOFF_STEPS_MS = [1000, 2000, 5000, 10000];

function backendOrigin(): string {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

export class SiteEventStream {
  private source: EventSource | null = null;
  private attempt = 0;
  private closedByCaller = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private siteId: string,
    private handlers: SseHandlers
  ) {}

  connect(): void {
    this.closedByCaller = false;
    this.open();
  }

  close(): void {
    this.closedByCaller = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.source?.close();
    this.source = null;
    this.handlers.onStateChange?.('closed');
  }

  private open(): void {
    this.handlers.onStateChange?.(this.attempt === 0 ? 'connecting' : 'reconnecting');
    const url = `${backendOrigin()}/api/events/stream?site_id=${encodeURIComponent(this.siteId)}`;
    const source = new EventSource(url);
    this.source = source;

    source.onopen = () => {
      this.attempt = 0;
      this.handlers.onStateChange?.('open');
    };

    source.addEventListener('plan.updated', (evt) => {
      this.dispatch(evt, this.handlers.onPlanUpdated);
    });
    source.addEventListener('telemetry.updated', (evt) => {
      this.dispatch(evt, this.handlers.onTelemetryUpdated);
    });
    source.addEventListener('alert.created', (evt) => {
      this.dispatch(evt, this.handlers.onAlertCreated);
    });

    source.onerror = () => {
      source.close();
      if (this.closedByCaller) return;
      const delay = BACKOFF_STEPS_MS[Math.min(this.attempt, BACKOFF_STEPS_MS.length - 1)];
      this.attempt += 1;
      this.handlers.onStateChange?.('reconnecting');
      this.reconnectTimer = setTimeout(() => this.open(), delay);
    };
  }

  private dispatch(evt: MessageEvent, handler?: (data: unknown) => void) {
    if (!handler) return;
    try {
      handler(JSON.parse(evt.data));
    } catch {
      // A malformed frame must not take down a live dashboard (FE_DESIGN.md §10).
    }
  }
}
