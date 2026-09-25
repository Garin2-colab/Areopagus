import { NextResponse } from "next/server";
import { modalAuthHeaders } from "@/lib/modal-auth";
import { getMutateUrl, validateImagePayload } from "@/lib/modal";
import { revalidateTag } from "next/cache";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const validationError = validateImagePayload(body?.image_base64);
    if (validationError) {
      return NextResponse.json({ ok: false, error: validationError }, { status: 400 });
    }

    const mutateUrl = getMutateUrl();

    if (!mutateUrl) {
      return NextResponse.json(
        { error: "Modal endpoint environment variables are not configured." },
        { status: 500 }
      );
    }

    const payload = {
      action: "upload_inspiration",
      ...body
    };

    const response = await fetch(mutateUrl, {
      method: "POST",
      headers: modalAuthHeaders(),
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      throw new Error(`Modal upload-inspiration endpoint failed with status ${response.status} (URL: ${mutateUrl})`);
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
      { ok: false, error: error instanceof Error ? error.message : "Inspiration upload failed." },
      { status: 500 }
    );
  }
}
