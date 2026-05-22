import { revalidateTag } from "next/cache";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    revalidateTag("history", "max");
    return NextResponse.json({ revalidated: true, now: Date.now() });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to revalidate" },
      { status: 500 }
    );
  }
}

export async function POST() {
  try {
    revalidateTag("history", "max");
    return NextResponse.json({ revalidated: true, now: Date.now() });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to revalidate" },
      { status: 500 }
    );
  }
}
