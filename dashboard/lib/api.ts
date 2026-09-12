/**
 * Shared fetch helper for the dashboard.
 *
 * Every call goes through the BFF (`app/api/[...path]/route.ts`), i.e. a relative `/api/...`
 * path — never the backend's own origin directly. FE_DESIGN.md §11 / REPO_STRUCTURE.md §5.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiGet<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const query = params
    ? '?' +
      Object.entries(params)
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
        .join('&')
    : '';
  const res = await fetch(`/api/${path}${query}`, { cache: 'no-store' });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = undefined;
    }
    throw new ApiError(`GET /api/${path} failed with ${res.status}`, res.status, body);
  }
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`/api/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = undefined;
    }
    throw new ApiError(`POST /api/${path} failed with ${res.status}`, res.status, body);
  }
  return res.json() as Promise<T>;
}

/** The default site until multi-site selection exists — must match settings.default_site_id. */
export const DEFAULT_SITE_ID = 'Dharavi Microgrid';
