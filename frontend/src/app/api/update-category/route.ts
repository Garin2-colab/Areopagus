import { NextResponse } from "next/server";
import { revalidateTag } from "next/cache";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getModalUpdateCategoryUrl() {
  const saveUrl = (process.env.MODAL_SAVE_URL || "").trim();
  const apiUrl = (process.env.MODAL_API_URL || "").trim();
  const statusUrl = (process.env.MODAL_STATUS_URL || "").trim();

  const referenceUrl = saveUrl || apiUrl || statusUrl;
  if (!referenceUrl) {
    return null;
  }

  return referenceUrl
    .replace("-save-endpoint.modal.run", "-update-category-endpoint.modal.run")
    .replace("-history-endpoint.modal.run", "-update-category-endpoint.modal.run")
    .replace("-status-endpoint.modal.run", "-update-category-endpoint.modal.run")
    .replace("-pulse-endpoint.modal.run", "-update-category-endpoint.modal.run")
    .replace("-get-image.modal.run", "-update-category-endpoint.modal.run");
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const updateUrl = getModalUpdateCategoryUrl();

    if (!updateUrl) {
      return NextResponse.json(
        { error: "Modal endpoint environment variables are not configured." },
        { status: 500 }
      );
    }

    const response = await fetch(updateUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      throw new Error(`Modal update-category endpoint failed with status ${response.status}`);
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
      { ok: false, error: error instanceof Error ? error.message : "Category update failed." },
      { status: 500 }
    );
  }
}
