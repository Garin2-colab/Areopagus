import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getHistoryUrl() {
  return process.env.MODAL_API_URL || process.env.NEXT_PUBLIC_MODAL_API_URL || "";
}

export async function POST() {
  try {
    // Resolve brain/references/ relative to the project root (one level up from frontend/)
    const projectRoot = path.resolve(process.cwd(), "..");
    const referencesDir = path.join(projectRoot, "brain", "references");
    const indexPath = path.join(projectRoot, "brain", ".brain-index.json");

    // Ensure directories exist
    fs.mkdirSync(referencesDir, { recursive: true });

    // Fetch history from Modal
    const historyUrl = getHistoryUrl();
    if (!historyUrl) {
      return NextResponse.json(
        { ok: false, error: "MODAL_API_URL is not configured." },
        { status: 500 }
      );
    }

    const historyRes = await fetch(historyUrl, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });

    if (!historyRes.ok) {
      throw new Error(`Failed to fetch history: ${historyRes.status}`);
    }

    const history = await historyRes.json();

    // Collect all items with images (inspiration + brain)
    type SyncItem = { id: string; image_url: string; keywords?: string[] };
    const items: SyncItem[] = [];

    for (const insp of history.inspiration || []) {
      if (insp.image_url) {
        items.push({ id: insp.id, image_url: insp.image_url, keywords: insp.keywords });
      }
    }

    for (const brain of history.brain || []) {
      if (brain.image_url) {
        items.push({ id: brain.id, image_url: brain.image_url, keywords: brain.keywords });
      }
    }

    let downloaded = 0;
    let skipped = 0;
    let failed = 0;
    const errors: string[] = [];

    for (const item of items) {
      // Determine file extension from URL or default to .webp
      const ext = ".webp";
      const filename = `${item.id}${ext}`;
      const filepath = path.join(referencesDir, filename);

      // Skip if already exists locally
      if (fs.existsSync(filepath)) {
        skipped++;
        continue;
      }

      try {
        // Resolve the image URL — handle relative URLs from the frontend proxy
        let imageUrl = item.image_url;
        if (imageUrl.startsWith("/api/")) {
          // This is a proxied URL — resolve it to the Modal image endpoint
          const params = new URL(imageUrl, "http://localhost").searchParams;
          const id = params.get("id");
          if (id) {
            // Construct direct Modal image URL
            const match = historyUrl.match(/https:\/\/([a-zA-Z0-9-]+)--/);
            const username = match ? match[1] : "heebok-lee";
            imageUrl = `https://${username}--areopagus-get-image.modal.run/?id=${id}`;
          }
        }

        const imgRes = await fetch(imageUrl);
        if (!imgRes.ok) {
          throw new Error(`HTTP ${imgRes.status}`);
        }

        const buffer = Buffer.from(await imgRes.arrayBuffer());

        // Validate we got actual image data (not an error page)
        if (buffer.length < 100) {
          throw new Error("Response too small to be a valid image");
        }

        fs.writeFileSync(filepath, buffer);
        downloaded++;
      } catch (err) {
        failed++;
        errors.push(`${item.id}: ${err instanceof Error ? err.message : "Unknown error"}`);
      }
    }

    // Update .brain-index.json with sync timestamp
    let index: Record<string, unknown> = {};
    try {
      if (fs.existsSync(indexPath)) {
        index = JSON.parse(fs.readFileSync(indexPath, "utf-8"));
      }
    } catch {
      index = {};
    }

    index.last_pull = new Date().toISOString();
    index.pull_stats = { downloaded, skipped, failed, total: items.length };
    fs.writeFileSync(indexPath, JSON.stringify(index, null, 2));

    return NextResponse.json({
      ok: true,
      downloaded,
      skipped,
      failed,
      total: items.length,
      directory: referencesDir,
      errors: errors.length > 0 ? errors.slice(0, 5) : undefined,
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
