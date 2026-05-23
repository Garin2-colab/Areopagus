import { NextResponse } from "next/server";
import { revalidateTag } from "next/cache";

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

function getModalImageUrl() {
  const saveUrl = (process.env.MODAL_SAVE_URL || "").trim();
  const apiUrl = (process.env.MODAL_API_URL || "").trim();
  const statusUrl = (process.env.MODAL_STATUS_URL || "").trim();
  const historyUrl = (process.env.MODAL_HISTORY_URL || "").trim();

  const referenceUrl = saveUrl || apiUrl || statusUrl || historyUrl;
  if (!referenceUrl) {
    return "https://heebok-lee--areopagus-get-image.modal.run";
  }

  if (referenceUrl.includes("get-image")) {
    return referenceUrl;
  }

  const match = referenceUrl.match(/https:\/\/([a-zA-Z0-9-]+)--([a-zA-Z0-9-]+)-[a-zA-Z0-9-]+\.modal\.run/);
  if (match) {
    return `https://${match[1]}--${match[2]}-get-image.modal.run`;
  }

  return "https://heebok-lee--areopagus-get-image.modal.run";
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
      throw new Error(`Modal replace-image endpoint failed with status ${response.status} (URL: ${mutateUrl})`);
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
