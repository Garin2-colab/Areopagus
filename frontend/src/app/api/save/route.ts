import { NextResponse } from "next/server";

export const runtime = "edge";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const saveUrl = process.env.MODAL_SAVE_URL;
    
    if (!saveUrl) {
      console.warn("MODAL_SAVE_URL is not configured.");
      return NextResponse.json({ ok: true, message: "Local save only (cloud URL not configured)" });
    }
    
    const response = await fetch(saveUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });
    
    if (!response.ok) {
      throw new Error(`Modal save endpoint failed with status ${response.status}`);
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
