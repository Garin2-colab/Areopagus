import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function modalHistoryUrl() {
  return process.env.MODAL_API_URL || process.env.NEXT_PUBLIC_MODAL_API_URL || "";
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const bypass = searchParams.get("bypass") === "true";

  const endpoint = modalHistoryUrl();
  if (!endpoint) {
    return NextResponse.json(
      {
        error: "MODAL_API_URL is not configured."
      },
      { status: 500 }
    );
  }

  try {
    const fetchOptions: RequestInit = {
      headers: {
        Accept: "application/json"
      }
    };

    if (bypass) {
      fetchOptions.cache = "no-store";
    } else {
      // Cache the response at the edge with revalidation tags
      (fetchOptions as any).next = { revalidate: 86400, tags: ["history"] };
    }

    const response = await fetch(endpoint, fetchOptions);

    const text = await response.text();
    const body = text ? JSON.parse(text) : null;

    return NextResponse.json(body, {
      status: response.ok ? 200 : response.status,
      headers: {
        "Cache-Control": bypass
          ? "no-store, must-revalidate"
          : "public, max-age=0, s-maxage=86400, stale-while-revalidate=3600"
      }
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Failed to fetch Modal history."
      },
      { status: 502 }
    );
  }
}
