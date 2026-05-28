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
    const v = searchParams.get("v");
    const format = searchParams.get("format");
    const isDev = searchParams.get("dev") === "true";
    if (!id) {
      return NextResponse.json({ error: "Missing id parameter" }, { status: 400 });
    }
 
    let modalImageUrlBase = getModalImageUrl();
    if (!modalImageUrlBase) {
      return NextResponse.json(
        { error: "Modal endpoint environment variables are not configured." },
        { status: 500 }
      );
    }
 
    if (isDev) {
      modalImageUrlBase = modalImageUrlBase.replace("-get-image.modal.run", "-get-image-dev.modal.run");
    }
 
    let targetUrl = `${modalImageUrlBase}?id=${encodeURIComponent(id)}`;
    if (v) {
      targetUrl += `&v=${encodeURIComponent(v)}`;
    }
    if (format) {
      targetUrl += `&format=${encodeURIComponent(format)}`;
    }
    let response = await fetch(targetUrl, {
      cache: "no-store",
    });

    if (!response.ok && response.status === 404) {
      // Bidirectional fallback
      let fallbackUrl = "";
      if (isDev) {
        // Fall back to production endpoint
        const prodBaseUrl = modalImageUrlBase.replace("-get-image-dev.modal.run", "-get-image.modal.run");
        fallbackUrl = `${prodBaseUrl}?id=${encodeURIComponent(id)}`;
      } else {
        // Fall back to dev endpoint
        const devBaseUrl = modalImageUrlBase.replace("-get-image.modal.run", "-get-image-dev.modal.run");
        fallbackUrl = `${devBaseUrl}?id=${encodeURIComponent(id)}`;
      }
      
      if (v) {
        fallbackUrl += `&v=${encodeURIComponent(v)}`;
      }
      if (format) {
        fallbackUrl += `&format=${encodeURIComponent(format)}`;
      }
      
      try {
        const fallbackResponse = await fetch(fallbackUrl, { cache: "no-store" });
        if (fallbackResponse.ok) {
          response = fallbackResponse;
        }
      } catch (err) {
        console.error("Fallback request failed:", err);
      }
    }

    if (!response.ok) {
      return NextResponse.json(
        { error: `Modal get_image failed with status ${response.status}` },
        { status: response.status }
      );
    }

    const contentType = response.headers.get("Content-Type") || "image/webp";
    const blob = await response.blob();
    return new Response(blob, {
      headers: {
        "Content-Type": contentType,
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
