import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getMutateUrl() {
  const saveUrl = (process.env.MODAL_SAVE_URL || "").trim();
  const apiUrl = (process.env.MODAL_API_URL || "").trim();
  const statusUrl = (process.env.MODAL_STATUS_URL || "").trim();

  const referenceUrl = saveUrl || apiUrl || statusUrl;
  if (!referenceUrl) return null;

  return referenceUrl
    .replace("-save-endpoint.modal.run", "-mutate-history-endpoint.modal.run")
    .replace("-history-endpoint.modal.run", "-mutate-history-endpoint.modal.run")
    .replace("-status-endpoint.modal.run", "-mutate-history-endpoint.modal.run")
    .replace("-pulse-endpoint.modal.run", "-mutate-history-endpoint.modal.run")
    .replace("-get-image.modal.run", "-mutate-history-endpoint.modal.run")
    .replace("-delete-post-endpoint.modal.run", "-mutate-history-endpoint.modal.run")
    .replace("-replace-image-endpoint.modal.run", "-mutate-history-endpoint.modal.run")
    .replace("-update-category-endpoint.modal.run", "-mutate-history-endpoint.modal.run");
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
