import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getModalImageUrl() {
  const saveUrl = (process.env.MODAL_SAVE_URL || "").trim();
  const apiUrl = (process.env.MODAL_API_URL || "").trim();
  const statusUrl = (process.env.MODAL_STATUS_URL || "").trim();

  const referenceUrl = saveUrl || apiUrl || statusUrl;
  if (!referenceUrl) {
    return null;
  }

  return referenceUrl
    .replace("-save-endpoint.modal.run", "-get-image.modal.run")
    .replace("-history-endpoint.modal.run", "-get-image.modal.run")
    .replace("-status-endpoint.modal.run", "-get-image.modal.run")
    .replace("-pulse-endpoint.modal.run", "-get-image.modal.run");
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get("id");
    if (!id) {
      return NextResponse.json({ error: "Missing id parameter" }, { status: 400 });
    }

    const modalImageUrlBase = getModalImageUrl();
    if (!modalImageUrlBase) {
      return NextResponse.json(
        { error: "Modal endpoint environment variables are not configured." },
        { status: 500 }
      );
    }

    const targetUrl = `${modalImageUrlBase}?id=${encodeURIComponent(id)}`;
    const response = await fetch(targetUrl, {
      cache: "no-store",
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Modal get_image failed with status ${response.status}` },
        { status: response.status }
      );
    }

    const blob = await response.blob();
    return new Response(blob, {
      headers: {
        "Content-Type": "image/webp",
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to proxy image request." },
      { status: 502 }
    );
  }
}
