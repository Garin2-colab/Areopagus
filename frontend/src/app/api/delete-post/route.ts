import { NextResponse } from "next/server";
import { revalidateTag } from "next/cache";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getModalDeleteUrl() {
  const saveUrl = (process.env.MODAL_SAVE_URL || "").trim();
  const apiUrl = (process.env.MODAL_API_URL || "").trim();
  const statusUrl = (process.env.MODAL_STATUS_URL || "").trim();

  const referenceUrl = saveUrl || apiUrl || statusUrl;
  if (!referenceUrl) {
    return null;
  }

  return referenceUrl
    .replace("-save-endpoint.modal.run", "-delete-post-endpoint.modal.run")
    .replace("-history-endpoint.modal.run", "-delete-post-endpoint.modal.run")
    .replace("-status-endpoint.modal.run", "-delete-post-endpoint.modal.run")
    .replace("-pulse-endpoint.modal.run", "-delete-post-endpoint.modal.run")
    .replace("-get-image.modal.run", "-delete-post-endpoint.modal.run");
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const deleteUrl = getModalDeleteUrl();

    if (!deleteUrl) {
      return NextResponse.json(
        { error: "Modal endpoint environment variables are not configured." },
        { status: 500 }
      );
    }

    const response = await fetch(deleteUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      throw new Error(`Modal delete endpoint failed with status ${response.status}`);
    }

    const data = await response.json();

    if (data.ok) {
      try {
        revalidateTag("history", "max");
      } catch (err) {
        console.error("Failed to revalidate cache tag:", err);
      }
    }

    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Delete post failed." },
      { status: 500 }
    );
  }
}
