import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function modalHistoryUrl() {
  return process.env.MODAL_API_URL || process.env.NEXT_PUBLIC_MODAL_API_URL || "";
}

export async function GET() {
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
    const response = await fetch(endpoint, {
      cache: "no-store",
      headers: {
        Accept: "application/json"
      }
    });

    const text = await response.text();
    const body = text ? JSON.parse(text) : null;

    return NextResponse.json(body, {
      status: response.ok ? 200 : response.status
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
