import { NextResponse } from "next/server";
import { modalAuthHeaders } from "@/lib/modal-auth";
import { getMutateUrl } from "@/lib/modal";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const mutateUrl = getMutateUrl();
    if (!mutateUrl) {
      console.warn("MODAL_SAVE_URL is not configured.");
      return NextResponse.json({ ok: false, error: "Cloud URL not configured" }, { status: 404 });
    }

    const response = await fetch(mutateUrl, {
      method: "POST",
      headers: modalAuthHeaders(),
      body: JSON.stringify({ action: "load_agents" }),
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error(`Modal save endpoint failed with status ${response.status} (URL: ${mutateUrl})`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Load failed." },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const mutateUrl = getMutateUrl();
    
    if (!mutateUrl) {
      console.warn("MODAL_SAVE_URL is not configured.");
      return NextResponse.json(
        { ok: false, error: "Cloud save is not configured (MODAL_SAVE_URL missing)." },
        { status: 503 }
      );
    }
    
    const payload = {
      action: "save",
      ...body
    };
    
    const response = await fetch(mutateUrl, {
      method: "POST",
      headers: modalAuthHeaders(),
      body: JSON.stringify(payload)
    });
    
    if (!response.ok) {
      throw new Error(`Modal save endpoint failed with status ${response.status} (URL: ${mutateUrl})`);
    }
    
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Save failed." },
      { status: 500 }
    );
  }
}

