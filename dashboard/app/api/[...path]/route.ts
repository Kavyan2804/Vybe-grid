/**
 * BFF proxy — the only place `dashboard/` talks to the backend.
 *
 * REPO_STRUCTURE.md §5: "app/api/ # BFF only — proxies to the backend, never touches Postgres."
 * One catch-all route forwards every `/api/*` GET request (query string included) to
 * `BACKEND_URL`, so adding a new backend endpoint never needs a new proxy file.
 */
import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  const path = params.path.join('/');
  const search = request.nextUrl.search;
  const target = `${BACKEND_URL}/api/${path}${search}`;

  try {
    const backendResponse = await fetch(target, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    const body = await backendResponse.text();
    return new NextResponse(body, {
      status: backendResponse.status,
      headers: { 'Content-Type': backendResponse.headers.get('content-type') || 'application/json' },
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: 'backend_unreachable',
        message: `Could not reach the backend at ${BACKEND_URL}.`,
        detail: { target },
      },
      { status: 502 }
    );
  }
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  const path = params.path.join('/');
  const target = `${BACKEND_URL}/api/${path}`;
  const body = await request.text();

  try {
    const backendResponse = await fetch(target, {
      method: 'POST',
      headers: { 'Content-Type': request.headers.get('content-type') || 'application/json' },
      body,
      cache: 'no-store',
    });
    const responseBody = await backendResponse.text();
    return new NextResponse(responseBody, {
      status: backendResponse.status,
      headers: { 'Content-Type': backendResponse.headers.get('content-type') || 'application/json' },
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: 'backend_unreachable',
        message: `Could not reach the backend at ${BACKEND_URL}.`,
        detail: { target },
      },
      { status: 502 }
    );
  }
}
