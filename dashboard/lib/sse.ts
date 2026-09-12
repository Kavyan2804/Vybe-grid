import { API_BASE, DEFAULT_SITE_ID } from './api';

export type TelemetryEvent = {
  type?: string;
  site_id?: string;
  ts?: string;
  payload?: unknown;
};

export function createTelemetryStream(
  onMessage: (event: TelemetryEvent) => void,
  options: { siteId?: string; onError?: (error: Event) => void } = {},
) {
  if (typeof window === 'undefined') {
    return { close() {} };
  }

  const siteId = encodeURIComponent(options.siteId ?? DEFAULT_SITE_ID);
  const source = new EventSource(`${API_BASE}/events?site_id=${siteId}`);

  source.onmessage = (message) => {
    try {
      onMessage(JSON.parse(message.data) as TelemetryEvent);
    } catch {
      onMessage({ type: 'raw', payload: message.data });
    }
  };

  if (options.onError) {
    source.onerror = options.onError;
  }

  return source;
}
