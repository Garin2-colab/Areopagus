"use client";

import { useEffect, useRef, useState } from "react";
import { Bolt, Minus, Plus, Save } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type ModelName = "GPT-Image-2" | "Gemini-3-Pro";

type AgentRecord = {
  id: string;
  name: string;
  persona: string;
  model: ModelName;
  heartbeatMinutes: number;
  referenceImages?: string[];
};

type StoredAgentsPayload = {
  updatedAt: string;
  personaCount: number;
  agents: AgentRecord[];
};

const STORAGE_KEY = "areopagus.agent-personas.v1";

const DEFAULT_PERSONA = "A minimalist avant-garde fashion curator. Aesthetic: Brutalist structures, silk drapery, high-contrast cinematic lighting, monochromatic palette.";

const DEFAULT_AGENTS: AgentRecord[] = [
  {
    id: "agent-1-gothic-anatomist",
    name: "Agent 01",
    persona: [
      "The Gothic Anatomist",
      "Visual Persona & Logic:",
      "Stance: Obsessed with the intersection of Savile Row precision and organic decay.",
      "Visual Priorities: Sharp, exaggerated silhouettes; corsetry as armor; intricate embroidery inspired by biological skeletons and bird plumage.",
      "Materials: Heavy wool, distressed leather, bird feathers, and tarnished silver.",
      "Behavior:",
      "Initiate: High-drama, theatrical compositions set in industrial or natural ruins.",
      'Critique: Brutally dismissive of "flat" designs; demands emotional weight and structural integrity.',
      "Pivot: Adds dark, romantic elements to sterile concepts (e.g., adding lace to concrete)."
    ].join("\n"),
    model: "GPT-Image-2",
    heartbeatMinutes: 15
  },
  {
    id: "agent-2-fluid-biomorph",
    name: "Agent 02",
    persona: [
      "The Fluid Biomorph",
      "Visual Persona & Logic:",
      "Stance: A seeker of biomimicry through advanced computational craft.",
      "Visual Priorities: Volumetric, 3D-printed structures that mimic fluid dynamics, magnetic fields, or microscopic organisms.",
      "Materials: Transparent polymers, laser-cut synthetics, kinetic fabrics that appear to be in constant motion.",
      "Behavior:",
      'Initiate: Ethereal, light-filled scenes focusing on the "impossible" geometry of the body.',
      "Critique: Rejects static or heavy silhouettes; looks for rhythmic patterns and scientific accuracy.",
      "Pivot: Translates rigid structures into transparent, flowing energy fields."
    ].join("\n"),
    model: "GPT-Image-2",
    heartbeatMinutes: 15
  }
];

function createAgent(index: number): AgentRecord {
  return {
    id: `agent-${index}-${Math.random().toString(36).slice(2, 8)}`,
    name: `Agent ${String(index).padStart(2, "0")}`,
    persona: DEFAULT_PERSONA,
    model: "GPT-Image-2",
    heartbeatMinutes: 15,
    referenceImages: []
  };
}

function sanitizeClientImageUrl(url: string | undefined): string {
  if (!url) return "";
  if (url.includes("-get-image.modal.run")) {
    const match = url.match(/[?&]id=([^&]+)/);
    if (match && match[1]) {
      const vMatch = url.match(/[?&]v=([^&]+)/);
      const vParam = vMatch ? `&v=${vMatch[1]}` : "";
      return `/api/image?id=${match[1]}${vParam}`;
    }
  }
  return url;
}

function isModelName(value: unknown): value is ModelName {
  return value === "GPT-Image-2" || value === "Gemini-3-Pro";
}

function normalizeStoredAgent(value: unknown, index: number): AgentRecord | null {
  if (!value || typeof value !== "object") return null;

  const candidate = value as Partial<AgentRecord>;
  const fallback = createAgent(index + 1);

  return {
    id: typeof candidate.id === "string" && candidate.id.trim() ? candidate.id : fallback.id,
    name: typeof candidate.name === "string" && candidate.name.trim() ? candidate.name : fallback.name,
    persona: typeof candidate.persona === "string" && candidate.persona.trim() ? candidate.persona : DEFAULT_PERSONA,
    model: isModelName(candidate.model) ? candidate.model : fallback.model,
    heartbeatMinutes:
      typeof candidate.heartbeatMinutes === "number" && Number.isFinite(candidate.heartbeatMinutes)
        ? candidate.heartbeatMinutes
        : fallback.heartbeatMinutes,
    referenceImages: Array.isArray(candidate.referenceImages) ? candidate.referenceImages : []
  };
}

function loadStoredAgents() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw);
    const storedAgents = Array.isArray(parsed)
      ? parsed
      : typeof parsed === "object" && parsed !== null && Array.isArray((parsed as StoredAgentsPayload).agents)
        ? (parsed as StoredAgentsPayload).agents
        : null;

    if (!storedAgents) return null;

    const agents = storedAgents
      .map((agent, index) => normalizeStoredAgent(agent, index))
      .filter((agent): agent is AgentRecord => agent !== null);

    return agents.length > 0 ? agents : null;
  } catch {
    return null;
  }
}

function saveAgents(agents: AgentRecord[]) {
  const payload: StoredAgentsPayload = {
    updatedAt: new Date().toISOString(),
    personaCount: agents.length,
    agents
  };

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  
  // Fire-and-forget sync to Modal
  fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }).catch((err) => console.error("Failed to sync agents to Modal:", err));

  return payload;
}

function nextAgentIndex(agents: AgentRecord[]) {
  return Math.max(agents.length + 1, 3);
}

type ManagementSidebarProps = {
  onPulseStart?: () => void | Promise<void>;
};

export function ManagementSidebar({ onPulseStart }: ManagementSidebarProps) {
  const nextAgentNumber = useRef(nextAgentIndex(DEFAULT_AGENTS));
  const agentsRef = useRef(DEFAULT_AGENTS);
  const [agents, setAgents] = useState<AgentRecord[]>(DEFAULT_AGENTS);
  const [agentsLoaded, setAgentsLoaded] = useState(false);
  const [pulsePending, setPulsePending] = useState(false);
  const [pulseMessage, setPulseMessage] = useState<string | null>(null);

  useEffect(() => {
    const storedAgents = loadStoredAgents();
    if (storedAgents) {
      nextAgentNumber.current = nextAgentIndex(storedAgents);
      agentsRef.current = storedAgents;
      setAgents(storedAgents);
    }
    setAgentsLoaded(true);
  }, []);

  useEffect(() => {
    if (!agentsLoaded) return;
    agentsRef.current = agents;
    saveAgents(agents);
  }, [agents, agentsLoaded]);

  useEffect(() => {
    return () => {
      if (agentsLoaded) {
        saveAgents(agentsRef.current);
      }
    };
  }, [agentsLoaded]);

  const commitAgents = (updater: (current: AgentRecord[]) => AgentRecord[]) => {
    setAgents((current) => {
      const nextAgents = updater(current);
      agentsRef.current = nextAgents;
      saveAgents(nextAgents);
      return nextAgents;
    });
  };

  const saveCurrentAgents = () => {
    const payload = saveAgents(agentsRef.current);
    setPulseMessage(`Saved ${payload.personaCount} personas.`);
  };

  const addAgent = () => {
    commitAgents((current) => [...current, createAgent(nextAgentNumber.current++)]);
  };

  const updateAgent = (id: string, patch: Partial<AgentRecord>) => {
    commitAgents((current) => current.map((agent) => (agent.id === id ? { ...agent, ...patch } : agent)));
  };

  const removeAgent = (id: string) => {
    commitAgents((current) => (current.length > 1 ? current.filter((agent) => agent.id !== id) : current));
  };

  const pulse = async () => {
    setPulsePending(true);
    setPulseMessage(null);
    saveAgents(agentsRef.current);

    try {
      await onPulseStart?.();
      const response = await fetch("/api/pulse", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          agents: agents.map((agent) => ({
            ...agent,
            active: true,
            selected_model: agent.model
          }))
        })
      });

      const data = (await response.json()) as { message?: string; error?: string };
      if (!response.ok) {
        throw new Error(data.error || "Pulse failed");
      }

      setPulseMessage(data.message || "Pulse dispatched to the orchestrator.");
    } catch (error) {
      setPulseMessage(error instanceof Error ? error.message : "Pulse failed.");
    } finally {
      setPulsePending(false);
    }
  };

  const handleUploadStyle = (agentId: string, index: number) => {
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "image/*";
    fileInput.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = async (event) => {
        const base64Data = event.target?.result as string;
        try {
          const response = await fetch("/api/replace-image", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              image_id: `ref_style_${agentId}_${index}`,
              image_base64: base64Data,
              mime_type: file.type,
            }),
          });
          const result = await response.json();
          if (!response.ok || !result.ok) {
            throw new Error(result.error || "Upload failed");
          }

          const uploadedUrl = result.url || `/api/image?id=ref_style_${agentId}_${index}&v=${Math.floor(Date.now() / 1000)}`;

          setAgents((current) =>
            current.map((agent) => {
              if (agent.id !== agentId) return agent;
              const nextRefs = [...(agent.referenceImages || [])];
              while (nextRefs.length <= index) {
                nextRefs.push("");
              }
              nextRefs[index] = uploadedUrl;
              return { ...agent, referenceImages: nextRefs };
            })
          );
        } catch (err) {
          console.error("Style upload failed:", err);
          alert(err instanceof Error ? err.message : "Upload failed");
        }
      };
      reader.readAsDataURL(file);
    };
    fileInput.click();
  };

  const handleClearStyle = (agentId: string, index: number) => {
    setAgents((current) =>
      current.map((agent) => {
        if (agent.id !== agentId) return agent;
        const nextRefs = [...(agent.referenceImages || [])];
        if (index < nextRefs.length) {
          nextRefs[index] = "";
        }
        return { ...agent, referenceImages: nextRefs };
      })
    );
  };

  return (
    <Card className="rounded-[2rem] border-zinc-800/80 bg-zinc-950/75 shadow-2xl shadow-black/25 backdrop-blur-sm">
      <CardHeader className="border-b border-zinc-800/80 px-6 py-5">
        <div className="flex flex-col gap-4">
          <div className="grid gap-2 sm:grid-cols-3">

            <Button
              type="button"
              onClick={pulse}
              disabled={pulsePending}
              className="justify-center rounded-full border-zinc-700 bg-zinc-100 text-black hover:bg-zinc-200"
            >
              <Bolt className="mr-2 h-4 w-4" />
              {pulsePending ? "Pulsing..." : "Pulse"}
            </Button>
            <Button type="button" onClick={addAgent} variant="outline" className="justify-center rounded-full border-zinc-700">
              <Plus className="mr-2 h-4 w-4" />
              Add Agent
            </Button>
          </div>
          {pulseMessage ? <p className="text-xs leading-5 text-zinc-400">{pulseMessage}</p> : null}
        </div>
      </CardHeader>

      <CardContent className="space-y-4 px-4 py-4 md:px-5">
        {agents.map((agent, index) => (
          <Card key={agent.id} className="overflow-hidden rounded-[1.5rem] border-zinc-800 bg-black/55">
            <CardHeader className="flex-row items-start justify-between gap-3 border-b border-zinc-800/70 px-4 py-4">
              <div className="space-y-1">
                <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Agent {index + 1}</p>
                <Badge className="border-zinc-700 bg-zinc-950 text-zinc-300">{agent.model}</Badge>
              </div>
              <Button
                type="button"
                variant="ghost"
                onClick={() => removeAgent(agent.id)}
                className="h-8 rounded-full text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-50 px-4"
                aria-label={`Remove ${agent.name}`}
              >
                Delete
              </Button>
            </CardHeader>

            <CardContent className="space-y-4 px-4 py-4">
              <div className="space-y-2">
                <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Name</p>
                <Input
                  value={agent.name}
                  onChange={(event) => updateAgent(agent.id, { name: event.target.value })}
                  placeholder="Agent name"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Persona</p>
                  <p className="text-[10px] uppercase tracking-[0.28em] text-zinc-600">Markdown supported</p>
                </div>
                <Textarea
                  value={agent.persona}
                  onChange={(event) => updateAgent(agent.id, { persona: event.target.value })}
                  placeholder="Describe the agent's worldview, tone, and editing preferences."
                  className="min-h-[164px]"
                />
                <p className="text-xs leading-5 text-zinc-500">
                  Use Markdown for bullets, emphasis, and short sections. This keeps long personas readable.
                </p>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Style References (2x5 Grid)</p>
                  <p className="text-[10px] uppercase tracking-[0.28em] text-zinc-600">Click a slot to upload</p>
                </div>
                <div className="grid grid-cols-5 gap-2">
                  {Array.from({ length: 10 }).map((_, i) => {
                    const imgUrl = agent.referenceImages?.[i];
                    const hasImage = typeof imgUrl === "string" && imgUrl.trim().length > 0;
                    const displayUrl = hasImage ? sanitizeClientImageUrl(imgUrl) : null;

                    return (
                      <div
                        key={i}
                        className={cn(
                          "group relative aspect-square w-full rounded-xl overflow-hidden border flex items-center justify-center transition-colors cursor-pointer",
                          hasImage
                            ? "border-zinc-800 bg-zinc-900/60"
                            : "border-dashed border-zinc-800 hover:border-zinc-600 hover:bg-zinc-900/50 bg-zinc-950"
                        )}
                        onClick={() => {
                          if (!hasImage) {
                            handleUploadStyle(agent.id, i);
                          }
                        }}
                      >
                        {displayUrl ? (
                          <>
                            <img
                              src={displayUrl}
                              alt={`Style Ref ${i + 1}`}
                              className="w-full h-full object-cover"
                            />
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleClearStyle(agent.id, i);
                              }}
                              className="absolute inset-0 bg-black/70 opacity-0 group-hover:opacity-100 flex items-center justify-center text-[10px] uppercase tracking-wider text-red-400 font-bold transition-opacity"
                            >
                              Clear
                            </button>
                          </>
                        ) : (
                          <span className="text-zinc-600 group-hover:text-zinc-400 text-sm font-semibold">+</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Model Selection & Save</p>
                <div className="flex gap-2">
                  <select
                    value={agent.model}
                    onChange={(event) => updateAgent(agent.id, { model: event.target.value as ModelName })}
                    className="flex-1 rounded-2xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-400 focus:border-zinc-600 focus:text-zinc-100 focus:outline-none"
                  >
                    <option value="GPT-Image-2">GPT-Image-2</option>
                    <option value="Gemini-3-Pro">Gemini-3-Pro</option>
                  </select>
                  <Button
                    type="button"
                    onClick={saveCurrentAgents}
                    className="rounded-2xl border border-zinc-700 bg-zinc-100 px-4 text-black hover:bg-zinc-200"
                  >
                    <Save className="mr-2 h-4 w-4" />
                    Save
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Heartbeat</p>
                  <span className="text-xs text-zinc-300">{agent.heartbeatMinutes} times per day</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={5}
                  step={1}
                  value={agent.heartbeatMinutes}
                  onChange={(event) => updateAgent(agent.id, { heartbeatMinutes: parseInt(event.target.value, 10) })}
                  className="h-2 w-full cursor-pointer appearance-none rounded-full bg-zinc-800 accent-zinc-100"
                />
                <div className="flex justify-between text-[10px] uppercase tracking-[0.24em] text-zinc-600">
                  <span>1x/day</span>
                  <span>5x/day</span>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </CardContent>
    </Card>
  );
}
