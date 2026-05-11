import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function modalStatusUrl() {
  return process.env.MODAL_STATUS_URL || process.env.NEXT_PUBLIC_MODAL_STATUS_URL || "";
}

export async function GET() {
  const endpoint = modalStatusUrl();
  if (!endpoint) {
    return NextResponse.json(
      {
        error: "MODAL_STATUS_URL is not configured."
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
        error: error instanceof Error ? error.message : "Failed to fetch Modal status."
      },
      { status: 502 }
    );
  }
}
