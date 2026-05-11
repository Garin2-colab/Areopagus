import { execFile, spawn } from "child_process";
import { promises as fs } from "fs";
import path from "path";
import { promisify } from "util";

import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type PulseBody = {
  agents?: Array<Record<string, any>>;
};

type AgentConfig = Record<string, any> & {
  active: any;
  selected_model: any;
};

const VOLUME_NAME = "areopagus-data";
const REMOTE_AGENTS_CONFIG_PATH = "/agents_config.json";
const execFileAsync = promisify(execFile);

type ExecFileError = Error & {
  stdout?: string | Buffer;
  stderr?: string | Buffer;
};

function repoRoot() {
  return path.resolve(process.cwd(), "..");
}

function modalExecutable() {
  const root = repoRoot();
  const localModal = path.join(root, ".venv", "Scripts", "modal.exe");
  return localModal;
}

function modalEnvironment(extra: Record<string, string | undefined> = {}) {
  return {
    ...process.env,
    PYTHONIOENCODING: "utf-8",
    PYTHONUTF8: "1",
    ...extra
  };
}

function sanitizeAgents(agents: Array<Record<string, any>>): AgentConfig[] {
  return agents.map((agent) => ({
    ...agent,
    active: agent.active ?? true,
    selected_model: agent.selected_model ?? agent.model
  }));
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as PulseBody;
    const agents = Array.isArray(body.agents) ? body.agents : [];
    const sanitizedAgents = sanitizeAgents(agents);

    const config = {
      updated_at: new Date().toISOString(),
      agents: sanitizedAgents
    };

    const root = repoRoot();
    const configPath = path.join(root, "agents_config.json");
    await fs.writeFile(configPath, JSON.stringify(config, null, 2) + "\n", "utf-8");

    const modal = modalExecutable();
    const volumeArgs = ["volume", "put", "--force", VOLUME_NAME, configPath, REMOTE_AGENTS_CONFIG_PATH];
    const modalArgs = ["run", "orchestrator.py"];
    const agentsConfigJson = JSON.stringify(config);

    try {
      console.log(`[pulse] uploading agents config: ${modal} ${volumeArgs.join(" ")}`);
      const uploadResult = await execFileAsync(modal, volumeArgs, {
        cwd: root,
        env: modalEnvironment(),
        windowsHide: true,
        maxBuffer: 1024 * 1024 * 10
      });

      if (uploadResult.stdout) {
        process.stdout.write(`[pulse volume stdout] ${uploadResult.stdout}`);
      }

      if (uploadResult.stderr) {
        process.stderr.write(`[pulse volume stderr] ${uploadResult.stderr}`);
      }
    } catch (error) {
      const execError = error as ExecFileError;
      console.error("[pulse volume error]", execError);
      if (execError.stdout) {
        process.stdout.write(`[pulse volume stdout] ${execError.stdout.toString()}`);
      }
      if (execError.stderr) {
        process.stderr.write(`[pulse volume stderr] ${execError.stderr.toString()}`);
      }
      throw error;
    }

    console.log(
      `[pulse] running: ${modal} ${modalArgs.join(" ")} (${sanitizedAgents.length} agents: ${sanitizedAgents
        .map((agent) => agent.name || agent.id || "unnamed")
        .join(", ")})`
    );

    const child = spawn(modal, modalArgs, {
      cwd: root,
      env: modalEnvironment({
        AREOPAGUS_AGENTS_CONFIG_JSON: agentsConfigJson
      }),
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true
    });

    child.stdout?.on("data", (chunk) => {
      process.stdout.write(`[pulse stdout] ${chunk.toString()}`);
    });

    child.stderr?.on("data", (chunk) => {
      process.stderr.write(`[pulse stderr] ${chunk.toString()}`);
    });

    child.on("error", (error) => {
      console.error("[pulse spawn error]", error);
    });

    child.on("close", (code, signal) => {
      console.log(`[pulse exit] code=${code} signal=${signal ?? "none"}`);
    });

    return NextResponse.json({
      ok: true,
      volumePath: `${VOLUME_NAME}:${REMOTE_AGENTS_CONFIG_PATH}`,
      command: `${modal} ${modalArgs.join(" ")}`,
      message: `Pulse queued for ${sanitizedAgents.length} agents.`
    });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : "Pulse failed."
      },
      { status: 500 }
    );
  }
}
