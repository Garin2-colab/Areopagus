import { NextRequest, NextResponse } from "next/server";

/**
 * Gates every mutating API route behind the ADMIN_PIN env var (server-only).
 *
 * Reads are public (history, status, image); anything that writes — delete,
 * replace, upload, save, pulse, sync-brain — requires an "x-admin-pin" header
 * matching ADMIN_PIN. The client stores the PIN in localStorage after one
 * prompt (see src/lib/admin-client.ts).
 *
 * If ADMIN_PIN is unset the check FAILS CLOSED: mutations return 401 until
 * the variable is configured (set it in Vercel project env vars and locally
 * in .env.local).
 */

const EXEMPT_PATHS = ["/api/revalidate"];

export function middleware(request: NextRequest) {
  if (request.method === "GET" || request.method === "HEAD" || request.method === "OPTIONS") {
    return NextResponse.next();
  }

  const pathname = request.nextUrl.pathname;
  if (EXEMPT_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next();
  }

  const expected = (process.env.ADMIN_PIN || "").trim();
  const provided = (request.headers.get("x-admin-pin") || "").trim();

  if (!expected || !provided || provided !== expected) {
    return NextResponse.json(
      { ok: false, error: "Unauthorized. Provide the admin PIN via the x-admin-pin header." },
      { status: 401 }
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: "/api/:path*",
};
