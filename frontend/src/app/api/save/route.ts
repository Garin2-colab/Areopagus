import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getMutateUrl() {
  const saveUrl = (process.env.MODAL_SAVE_URL || "").trim();
  const apiUrl = (process.env.MODAL_API_URL || "").trim();
  const statusUrl = (process.env.MODAL_STATUS_URL || "").trim();
  const historyUrl = (process.env.MODAL_HISTORY_URL || "").trim();

  const referenceUrl = saveUrl || apiUrl || statusUrl || historyUrl;
  if (!referenceUrl) {
    return "https://heebok-lee--areopagus-mutate-history-endpoint.modal.run";
  }

  if (referenceUrl.includes("mutate-history-endpoint")) {
    return referenceUrl;
  }

  const match = referenceUrl.match(/https:\/\/([a-zA-Z0-9-]+)--([a-zA-Z0-9-]+)-[a-zA-Z0-9-]+\.modal\.run/);
  if (match) {
    return `https://${match[1]}--${match[2]}-mutate-history-endpoint.modal.run`;
  }

  return "https://heebok-lee--areopagus-mutate-history-endpoint.modal.run";
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const mutateUrl = getMutateUrl();
    
    if (!mutateUrl) {
      console.warn("MODAL_SAVE_URL is not configured.");
      return NextResponse.json({ ok: true, message: "Local save only (cloud URL not configured)" });
    }
    
    const payload = {
      action: "save",
      ...body
    };
    
    const response = await fetch(mutateUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
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
