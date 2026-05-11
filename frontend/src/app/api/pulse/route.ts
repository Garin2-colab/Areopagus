import { NextResponse } from "next/server";

export const runtime = "edge";
export const dynamic = "force-dynamic";

type PulseBody = {
  agents?: Array<Record<string, any>>;
};

function sanitizeAgents(agents: Array<Record<string, any>>) {
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

    const pulseUrl = process.env.MODAL_PULSE_URL;
    if (!pulseUrl) {
      throw new Error("MODAL_PULSE_URL is not configured.");
    }
    
    const response = await fetch(pulseUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(config)
    });
    
    if (!response.ok) {
      throw new Error(`Modal pulse endpoint failed with status ${response.status}`);
    }
    
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Pulse failed." },
      { status: 500 }
    );
  }
}
