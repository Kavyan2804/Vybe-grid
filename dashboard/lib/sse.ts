import { API_BASE, DEFAULT_SITE_ID, gridpilotFetch, type OverviewResponse } from './api';

export type SiteRealtimeEvent = {
  type: string;
  site_id?: string;
  subject?: string | null;
  event_id?: string | null;
  timestamp?: string;
  payload?: Record<string, unknown>;
};

const BACKOFF_MS = [1000, 2000, 5000, 10000];

function eventsUrl(siteId: string): string {
  // EventSource must hit the backend directly — the Next BFF buffers JSON responses.
  const backend =
    process.env.NEXT_PUBLIC_BACKEND_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    'http://127.0.0.1:8000';
  return `${backend.replace(/\/$/, '')}/api/events/stream?site_id=${encodeURIComponent(siteId)}`;
}

export type SiteStreamHandlers = {
  siteId?: string;
  onEvent?: (event: SiteRealtimeEvent) => void;
  onStatus?: (status: 'connected' | 'reconnecting' | 'disconnected') => void;
  onResync?: () => void | Promise<void>;
};

export function createSiteEventStream(handlers: SiteStreamHandlers = {}) {
  if (typeof window === 'undefined') {
    return { close() {} };
  }

  const siteId = handlers.siteId ?? DEFAULT_SITE_ID;
  let closed = false;
  let attempt = 0;
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const EVENT_NAMES = ['plan.updated', 'telemetry.updated', 'alert.created'] as const;

  const connect = () => {
    if (closed) return;
    handlers.onStatus?.(attempt === 0 ? 'connected' : 'reconnecting');
    source = new EventSource(eventsUrl(siteId));

    const forward = (raw: MessageEvent) => {
      try {
        handlers.onEvent?.(JSON.parse(String(raw.data)) as SiteRealtimeEvent);
      } catch {
        handlers.onEvent?.({ type: 'raw', payload: { data: raw.data } });
      }
    };

    for (const name of EVENT_NAMES) {
      source.addEventListener(name, forward as EventListener);
    }
    source.onopen = () => {
      attempt = 0;
      handlers.onStatus?.('connected');
      void handlers.onResync?.();
    };
    source.onerror = () => {
      source?.close();
      source = null;
      if (closed) return;
      handlers.onStatus?.('reconnecting');
      const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
      attempt += 1;
      timer = setTimeout(connect, delay);
    };
  };

  connect();

  return {
    close() {
      closed = true;
      if (timer) clearTimeout(timer);
      source?.close();
      handlers.onStatus?.('disconnected');
    },
  };
}

export async function refetchOverview(siteId = DEFAULT_SITE_ID): Promise<OverviewResponse> {
  return gridpilotFetch<OverviewResponse>(
    `/overview?site_id=${encodeURIComponent(siteId)}`,
  );
}

/** @deprecated Prefer createSiteEventStream */
export function createTelemetryStream(
  onMessage: (event: SiteRealtimeEvent) => void,
  options: { siteId?: string; onError?: (error: Event) => void } = {},
) {
  return createSiteEventStream({
    siteId: options.siteId,
    onEvent: onMessage,
    onStatus: (status) => {
      if (status === 'reconnecting' && options.onError) {
        options.onError(new Event('error'));
      }
    },
  });
}

void API_BASE;
