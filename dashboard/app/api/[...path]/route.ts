import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL =
  process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const path = params.path.join('/');
  const target = `${BACKEND_URL}/api/${path}${request.nextUrl.search}`;

  try {
    const response = await fetch(target, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') || 'application/json',
      },
    });
  } catch {
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

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const path = params.path.join('/');
  const target = `${BACKEND_URL}/api/${path}${request.nextUrl.search}`;

  try {
    const response = await fetch(target, {
      method: 'POST',
      headers: {
        'Content-Type': request.headers.get('content-type') || 'application/json',
      },
      body: await request.text(),
      cache: 'no-store',
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') || 'application/json',
      },
    });
  } catch {
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
