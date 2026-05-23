import { NextResponse } from "next/server";
import { revalidateTag } from "next/cache";

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

function getModalImageUrl() {
  const saveUrl = (process.env.MODAL_SAVE_URL || "").trim();
  const apiUrl = (process.env.MODAL_API_URL || "").trim();
  const statusUrl = (process.env.MODAL_STATUS_URL || "").trim();

  const referenceUrl = saveUrl || apiUrl || statusUrl;
  if (!referenceUrl) return null;

  return referenceUrl
    .replace("-save-endpoint.modal.run", "-get-image.modal.run")
    .replace("-history-endpoint.modal.run", "-get-image.modal.run")
    .replace("-status-endpoint.modal.run", "-get-image.modal.run")
    .replace("-pulse-endpoint.modal.run", "-get-image.modal.run");
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const mutateUrl = getMutateUrl();

    if (!mutateUrl) {
      return NextResponse.json(
        { error: "Modal endpoint environment variables are not configured." },
        { status: 500 }
      );
    }

    const payload = {
      action: "replace_image",
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
      throw new Error(`Modal replace-image endpoint failed with status ${response.status}`);
    }

    const data = await response.json();

    if (data.ok) {
      try {
        revalidateTag("history", "max");
      } catch (err) {
        console.error("Failed to revalidate cache tag:", err);
      }

      const modalImageBase = getModalImageUrl();
      if (modalImageBase) {
        const v = Math.floor(Date.now() / 1000);
        data.url = `${modalImageBase}?id=${encodeURIComponent(body.image_id)}&v=${v}`;
      }
    }

    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Image replacement failed." },
      { status: 500 }
    );
  }
}
