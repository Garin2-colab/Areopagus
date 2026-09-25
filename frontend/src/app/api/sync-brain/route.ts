import { NextResponse } from "next/server";
import path from "path";
import fs from "fs";
import { spawn } from "child_process";

const IS_VERCEL = process.env.VERCEL === "1";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET - Checks current sync status.
 */
export async function GET() {
  try {
    let rootDir = process.cwd();
    if (!fs.existsSync(path.join(rootDir, "sync_brain.py")) && fs.existsSync(path.join(rootDir, "..", "sync_brain.py"))) {
      rootDir = path.join(rootDir, "..");
    }
    const lockPath = path.join(rootDir, "brain", ".sync.lock");
    const statusPath = path.join(rootDir, "brain", ".sync-status.json");

    const isRunning = fs.existsSync(lockPath);
    let statusData = {
      status: isRunning ? "running" : "idle",
      current: 0,
      total: 0,
      synced: 0,
      errors: 0,
      skipped: 0,
    };

    if (fs.existsSync(statusPath)) {
      try {
        const fileContent = fs.readFileSync(statusPath, "utf-8");
        statusData = JSON.parse(fileContent);
      } catch (e) {
        console.error("Failed to parse status JSON:", e);
      }
    }

    // Double check status consistency
    const currentStatus = isRunning ? "running" : (statusData.status === "running" ? "completed" : statusData.status);

    return NextResponse.json({
      ok: true,
      in_progress: isRunning,
      status: currentStatus,
      current: statusData.current || 0,
      total: statusData.total || 0,
      downloaded: statusData.synced || 0,
      skipped: statusData.skipped || 0,
      failed: statusData.errors || 0,
      message: isRunning 
        ? `Syncing... (${statusData.current}/${statusData.total} files processed)` 
        : `Sync completed. ${statusData.synced} downloaded, ${statusData.skipped} skipped, ${statusData.errors} failed.`,
    });
  } catch (error) {
    console.error("[Sync GET] Error:", error);
    return NextResponse.json({ ok: false, error: "Failed to fetch sync status" }, { status: 500 });
  }
}

/**
 * POST - Spawns local ingestion pipeline (sync_brain.py) in the background.
 */
export async function POST() {
  if (IS_VERCEL) {
    // Serverless has no persistent filesystem; spawning sync_brain.py here
    // can neither work nor persist results. Run the sync locally instead.
    return NextResponse.json(
      { ok: false, error: "Brain sync is only available on a local (non-serverless) deployment." },
      { status: 501 }
    );
  }

  try {
    let rootDir = process.cwd();
    if (!fs.existsSync(path.join(rootDir, "sync_brain.py")) && fs.existsSync(path.join(rootDir, "..", "sync_brain.py"))) {
      rootDir = path.join(rootDir, "..");
    }

    const scriptPath = path.join(rootDir, "sync_brain.py");
    const lockPath = path.join(rootDir, "brain", ".sync.lock");
    const statusPath = path.join(rootDir, "brain", ".sync-status.json");

    // Check if lock file exists
    const isRunning = fs.existsSync(lockPath);
    if (isRunning) {
      return NextResponse.json({
        ok: true,
        in_progress: true,
        message: "Sync is already in progress.",
      });
    }

    if (!fs.existsSync(scriptPath)) {
      return NextResponse.json(
        { ok: false, error: `sync_brain.py not found at ${scriptPath}` },
        { status: 404 }
      );
    }

    let pythonPath = "python";
    const winVenv = path.join(rootDir, ".venv", "Scripts", "python.exe");
    const unixVenv = path.join(rootDir, ".venv", "bin", "python");

    if (fs.existsSync(winVenv)) {
      pythonPath = winVenv;
    } else if (fs.existsSync(unixVenv)) {
      pythonPath = unixVenv;
    }

    // Write initial status file
    const initialStatus = {
      status: "running",
      current: 0,
      total: 0,
      synced: 0,
      errors: 0,
      skipped: 0,
      updated_at: new Date().toISOString(),
    };
    fs.writeFileSync(statusPath, JSON.stringify(initialStatus, null, 2), "utf-8");

    console.log(`[Sync POST] Spawning background process: "${pythonPath}" "${scriptPath}"`);
    
    // Spawn python process detached
    const child = spawn(pythonPath, [scriptPath], {
      cwd: rootDir,
      detached: true,
      stdio: "ignore",
    });
    
    child.unref();

    return NextResponse.json({
      ok: true,
      in_progress: true,
      message: "Sync started in background.",
    });
  } catch (error) {
    console.error("[Sync POST] Error:", error);
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Failed to trigger sync" },
      { status: 500 }
    );
  }
}
