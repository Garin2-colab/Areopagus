import { NextResponse } from "next/server";
import { modalAuthHeaders } from "@/lib/modal-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getHistoryUrl() {
  return process.env.MODAL_API_URL || process.env.NEXT_PUBLIC_MODAL_API_URL || "";
}

/**
 * Sync endpoint — triggers a data refresh from the Modal backend.
 *
 * IMPORTANT: The local brain/ folder is the user's raw data.
 * This endpoint must NEVER write files into brain/.
 * It only fetches the latest state from Modal so the frontend can refresh.
 */
export async function POST() {
  try {
    const historyUrl = getHistoryUrl();
    if (!historyUrl) {
      return NextResponse.json(
        { ok: false, error: "MODAL_API_URL is not configured." },
        { status: 500 }
      );
    }

    // Fetch latest history from Modal to confirm connectivity and get counts
    const historyRes = await fetch(historyUrl, {
      cache: "no-store",
      headers: { Accept: "application/json", ...modalAuthHeaders() },
    });

    if (!historyRes.ok) {
      throw new Error(`Failed to fetch history: ${historyRes.status}`);
    }

    const history = await historyRes.json();

    const brainCount = (history.brain || []).length;
    const inspirationCount = (history.inspiration || []).length;
    const totalItems = brainCount + inspirationCount;

    return NextResponse.json({
      ok: true,
      message: `Synced. ${totalItems} items found (${brainCount} brain, ${inspirationCount} inspiration).`,
      brain_count: brainCount,
      inspiration_count: inspirationCount,
      total: totalItems,
    });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : "Sync failed.",
      },
      { status: 500 }
    );
  }
}
