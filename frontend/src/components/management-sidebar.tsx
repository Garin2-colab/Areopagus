"use client";

import { useEffect, useRef, useState } from "react";
import { Bolt, Minus, Plus, Save } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn, compressImage } from "@/lib/utils";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { StudioStatus } from "@/lib/useStudioStatus";

type ModelName = "GPT-Image-2" | "Gemini-3-Pro" | "Midjourney" | "Seedance-v2";

type AgentRecord = {
  id: string;
  name: string;
  persona: string;
  model: ModelName;
  heartbeatMinutes: number;
  referenceImages?: string[];
  active?: boolean;
};

type StoredAgentsPayload = {
  updatedAt: string;
  personaCount: number;
  agents: AgentRecord[];
};

const STORAGE_KEY = "areopagus.agent-personas.v1";

const DEFAULT_PERSONA = "A minimalist avant-garde fashion curator. Aesthetic: Brutalist structures, silk drapery, high-contrast cinematic lighting, monochromatic palette.";

const PHILOSOPHER_NAMES = [
  "Socrates", "Plato", "Aristotle", "Pythagoras", "Heraclitus", "Parmenides",
  "Zeno", "Epicurus", "Diogenes", "Democritus", "Anaximander", "Thales",
  "Empedocles", "Anaxagoras", "Protagoras", "Gorgias", "Epictetus", "Seneca",
  "Plotinus", "Chrysippus", "Pyrrho", "Theophrastus", "Hypatia", "Zenobia",
  "Aristippus"
];

function generateGreekPhilosopherName(existingNames: string[]): string {
  const normalizedExisting = existingNames.map(n => n.trim().toLowerCase());
  const available = PHILOSOPHER_NAMES.filter(
    name => !normalizedExisting.includes(name.toLowerCase())
  );
  if (available.length > 0) {
    const idx = Math.floor(Math.random() * available.length);
    return available[idx];
  }
  const baseName = PHILOSOPHER_NAMES[Math.floor(Math.random() * PHILOSOPHER_NAMES.length)];
  let counter = 2;
  while (normalizedExisting.includes(`${baseName.toLowerCase()} ${counter}`)) {
    counter++;
  }
  return `${baseName} ${counter}`;
}

const DEFAULT_AGENTS: AgentRecord[] = [
  {
    id: "agent-1-gothic-anatomist",
    name: "Socrates",
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
    name: "Plato",
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

function createAgent(index: number, existingNames: string[] = []): AgentRecord {
  return {
    id: `agent-${index}-${Math.random().toString(36).slice(2, 8)}`,
    name: generateGreekPhilosopherName(existingNames),
    persona: DEFAULT_PERSONA,
    model: "GPT-Image-2",
    heartbeatMinutes: 15,
    referenceImages: [],
    active: true
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
  return value === "GPT-Image-2" || value === "Gemini-3-Pro" || value === "Midjourney" || value === "Seedance-v2";
}

function normalizeStoredAgent(value: unknown, index: number, existingNames: string[]): AgentRecord | null {
  if (!value || typeof value !== "object") return null;

  const candidate = value as Partial<AgentRecord>;
  const fallback = createAgent(index + 1, existingNames);

  let name = typeof candidate.name === "string" && candidate.name.trim() ? candidate.name : fallback.name;
  if (name.startsWith("Agent ")) {
    name = generateGreekPhilosopherName(existingNames);
  }
  existingNames.push(name);

  return {
    id: typeof candidate.id === "string" && candidate.id.trim() ? candidate.id : fallback.id,
    name,
    persona: typeof candidate.persona === "string" && candidate.persona.trim() ? candidate.persona : DEFAULT_PERSONA,
    model: isModelName(candidate.model) ? candidate.model : fallback.model,
    heartbeatMinutes:
      typeof candidate.heartbeatMinutes === "number" && Number.isFinite(candidate.heartbeatMinutes)
        ? candidate.heartbeatMinutes
        : fallback.heartbeatMinutes,
    referenceImages: Array.isArray(candidate.referenceImages) ? candidate.referenceImages : [],
    active: typeof candidate.active === "boolean" ? candidate.active : true
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

    const existingNames: string[] = [];
    const agents = storedAgents
      .map((agent, index) => normalizeStoredAgent(agent, index, existingNames))
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
  status?: StudioStatus | null;
  onUnsavedChangeStateChange?: (hasUnsaved: boolean, unsavedAgentNames: string[]) => void;
};

export function ManagementSidebar({ onPulseStart, status, onUnsavedChangeStateChange }: ManagementSidebarProps) {
  const nextAgentNumber = useRef(nextAgentIndex(DEFAULT_AGENTS));
  const agentsRef = useRef(DEFAULT_AGENTS);
  const [agents, setAgents] = useState<AgentRecord[]>(DEFAULT_AGENTS);
  const [savedAgents, setSavedAgents] = useState<AgentRecord[]>(DEFAULT_AGENTS);
  const [agentsLoaded, setAgentsLoaded] = useState(false);
  const [pulsePending, setPulsePending] = useState(false);
  const [pulseMessage, setPulseMessage] = useState<string | null>(null);
  const [savedStatus, setSavedStatus] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let active = true;
    async function initAgents() {
      try {
        const response = await fetch("/api/save");
        if (response.ok) {
          const data = await response.json();
          if (data.ok && data.config && Array.isArray(data.config.agents)) {
            const existingNames: string[] = [];
            const loaded = data.config.agents
              .map((agent: any, idx: number) => {
                const result = normalizeStoredAgent(agent, idx, existingNames);
                if (result) existingNames.push(result.name);
                return result;
              })
              .filter((agent: any): agent is AgentRecord => agent !== null);
            if (loaded.length > 0 && active) {
              nextAgentNumber.current = nextAgentIndex(loaded);
              agentsRef.current = loaded;
              setAgents(loaded);
              setSavedAgents(loaded);
              
              const payload: StoredAgentsPayload = {
                updatedAt: new Date().toISOString(),
                personaCount: loaded.length,
                agents: loaded
              };
              window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
              setAgentsLoaded(true);
              return;
            }
          }
        }
      } catch (err) {
        console.warn("Failed to load agents from server, falling back to localStorage:", err);
      }

      if (!active) return;

      const storedAgents = loadStoredAgents();
      if (storedAgents) {
        nextAgentNumber.current = nextAgentIndex(storedAgents);
        agentsRef.current = storedAgents;
        setAgents(storedAgents);
        setSavedAgents(storedAgents);
      } else {
        setSavedAgents(DEFAULT_AGENTS);
      }
      setAgentsLoaded(true);
    }

    initAgents();
    return () => {
      active = false;
    };
  }, []);
  const lastReportedRef = useRef<string[]>([]);

  useEffect(() => {
    if (!agentsLoaded) return;
    
    const unsavedNames: string[] = [];
    agents.forEach((current) => {
      const saved = savedAgents.find((s) => s.id === current.id);
      if (!saved) {
        unsavedNames.push(current.name || "New Agent");
      } else {
        const isChanged =
          current.name !== saved.name ||
          current.persona !== saved.persona ||
          current.model !== saved.model ||
          current.heartbeatMinutes !== saved.heartbeatMinutes ||
          (current.active !== undefined ? current.active : true) !== (saved.active !== undefined ? saved.active : true) ||
          JSON.stringify(current.referenceImages || []) !== JSON.stringify(saved.referenceImages || []);
        if (isChanged) {
          unsavedNames.push(current.name || saved.name);
        }
      }
    });

    savedAgents.forEach((saved) => {
      if (!agents.some((current) => current.id === saved.id)) {
        unsavedNames.push(`${saved.name} (Deleted)`);
      }
    });

    const isDifferent =
      unsavedNames.length !== lastReportedRef.current.length ||
      unsavedNames.some((name, i) => name !== lastReportedRef.current[i]);

    if (isDifferent) {
      lastReportedRef.current = unsavedNames;
      onUnsavedChangeStateChange?.(unsavedNames.length > 0, unsavedNames);
    }
  }, [agents, savedAgents, agentsLoaded, onUnsavedChangeStateChange]);

  const commitAgents = (updater: (current: AgentRecord[]) => AgentRecord[]) => {
    setAgents((current) => {
      const nextAgents = updater(current);
      agentsRef.current = nextAgents;
      return nextAgents;
    });
  };

  const hasUnsavedChanges = (agentId: string) => {
    const current = agents.find((a) => a.id === agentId);
    const saved = savedAgents.find((a) => a.id === agentId);
    if (!current) return false;
    if (!saved) return true;
    return (
      current.name !== saved.name ||
      current.persona !== saved.persona ||
      current.model !== saved.model ||
      current.heartbeatMinutes !== saved.heartbeatMinutes ||
      (current.active !== undefined ? current.active : true) !== (saved.active !== undefined ? saved.active : true) ||
      JSON.stringify(current.referenceImages || []) !== JSON.stringify(saved.referenceImages || [])
    );
  };

  const saveAgent = (agentId: string) => {
    setSavedAgents(agents);
    agentsRef.current = agents;
    const payload = saveAgents(agents);

    setSavedStatus((prev) => ({ ...prev, [agentId]: true }));
    setTimeout(() => {
      setSavedStatus((prev) => ({ ...prev, [agentId]: false }));
    }, 3000);
  };

  const addAgent = () => {
    commitAgents((current) => {
      const existingNames = current.map((a) => a.name);
      return [...current, createAgent(nextAgentNumber.current++, existingNames)];
    });
  };

  const updateAgent = (id: string, patch: Partial<AgentRecord>) => {
    commitAgents((current) => current.map((agent) => (agent.id === id ? { ...agent, ...patch } : agent)));
  };

  const toggleAgentActive = (id: string) => {
    setAgents((current) => {
      const nextAgents = current.map((agent) => {
        if (agent.id === id) {
          return { ...agent, active: agent.active !== false ? false : true };
        }
        return agent;
      });
      agentsRef.current = nextAgents;
      setSavedAgents(nextAgents);
      saveAgents(nextAgents);
      return nextAgents;
    });
  };

  const removeAgent = (id: string) => {
    commitAgents((current) => (current.length > 1 ? current.filter((agent) => agent.id !== id) : current));
  };

  const pulse = async () => {
    setPulsePending(true);
    setPulseMessage(null);

    // Save all agents on pulse
    setSavedAgents(agents);
    agentsRef.current = agents;
    saveAgents(agents);

    // Flash saved status on all active agents
    const nextSavedStatus: Record<string, boolean> = {};
    agents.forEach((a) => {
      nextSavedStatus[a.id] = true;
    });
    setSavedStatus(nextSavedStatus);
    setTimeout(() => {
      setSavedStatus((prev) => {
        const reset: Record<string, boolean> = {};
        Object.keys(prev).forEach((k) => {
          reset[k] = false;
        });
        return reset;
      });
    }, 3000);

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

      try {
        const base64Data = await compressImage(file);
        const response = await fetch("/api/replace-image", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            image_id: `ref_style_${agentId}_${index}`,
            image_base64: base64Data,
            mime_type: "image/jpeg",
          }),
        });

        if (!response.ok) {
          let errMsg = `Upload failed with status ${response.status}`;
          try {
            const errorData = await response.json();
            errMsg = errorData.error || errMsg;
          } catch {
            try {
              const txt = await response.text();
              if (txt && txt.length < 200) {
                errMsg = txt;
              }
            } catch {}
          }
          throw new Error(errMsg);
        }

        const result = await response.json();
        if (!result.ok) {
          throw new Error(result.error || "Upload failed");
        }

        const uploadedUrl = result.url || `/api/image?id=ref_style_${agentId}_${index}&v=${Math.floor(Date.now() / 1000)}`;

        setAgents((current) => {
          const next = current.map((agent) => {
            if (agent.id !== agentId) return agent;
            const nextRefs = [...(agent.referenceImages || [])];
            while (nextRefs.length <= index) {
              nextRefs.push("");
            }
            nextRefs[index] = uploadedUrl;
            return { ...agent, referenceImages: nextRefs };
          });
          saveAgents(next);
          setSavedAgents(next);
          agentsRef.current = next;
          return next;
        });
      } catch (err) {
        console.error("Style upload failed:", err);
        alert(err instanceof Error ? err.message : "Upload failed");
      }
    };
    fileInput.click();
  };

  const handleClearStyle = (agentId: string, index: number) => {
    setAgents((current) => {
      const next = current.map((agent) => {
        if (agent.id !== agentId) return agent;
        const nextRefs = [...(agent.referenceImages || [])];
        if (index < nextRefs.length) {
          nextRefs[index] = "";
        }
        return { ...agent, referenceImages: nextRefs };
      });
      saveAgents(next);
      setSavedAgents(next);
      agentsRef.current = next;
      return next;
    });
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <div className="grid gap-2 grid-cols-2">
 
          <Button
            type="button"
            onClick={pulse}
            disabled={pulsePending}
            className="justify-center rounded-full border-[#D8D4CC] bg-[#252422] text-[#FAF9F6] hover:bg-black hover:text-white hover:border-[#252422]"
          >
            <Bolt className="mr-2 h-4 w-4" />
            {pulsePending ? "Pulsing..." : "Pulse"}
          </Button>
          <Button
            type="button"
            onClick={addAgent}
            variant="outline"
            className="justify-center rounded-full border-[#D8D4CC] bg-white text-[#44423E] hover:bg-[#F5F2EB] hover:text-[#252422]"
          >
            <Plus className="mr-2 h-4 w-4" />
            Add Agent
          </Button>
        </div>
        {pulseMessage ? <p className="text-xs leading-5 text-[#858076] font-medium">{pulseMessage}</p> : null}
      </div>
 
      <div className="border-t border-[#D8D4CC]/60 pt-5">
        <Tabs defaultValue="agents" className="w-full">
          <TabsList className="grid w-full grid-cols-2 h-auto rounded-2xl bg-[#F5F2EB]/70 p-1 mb-6 border border-[#D8D4CC]/50">
            <TabsTrigger
              value="agents"
              className="rounded-xl text-xs font-semibold py-2 transition-all data-[state=active]:bg-white data-[state=active]:text-[#252422] data-[state=active]:shadow-sm data-[state=active]:border-transparent text-[#858076] hover:text-[#252422]"
            >
              Agents Configuration
            </TabsTrigger>
            <TabsTrigger
              value="logs"
              className="rounded-xl text-xs font-semibold py-2 transition-all data-[state=active]:bg-white data-[state=active]:text-[#252422] data-[state=active]:shadow-sm data-[state=active]:border-transparent text-[#858076] hover:text-[#252422]"
            >
              Execution Logs
            </TabsTrigger>
          </TabsList>
 
          <TabsContent value="agents" className="space-y-4 outline-none">
            {agents.map((agent, index) => (
              <Card 
                key={agent.id} 
                className={cn(
                  "overflow-hidden rounded-[1.5rem] border bg-white shadow-none transition-all duration-200",
                  agent.active === false 
                    ? "border-[#D8D4CC]/50 bg-gray-50/50" 
                    : "border-[#D8D4CC]/80"
                )}
              >
                <CardHeader className="flex-row items-start justify-between gap-3 border-b border-[#D8D4CC]/50 px-4 py-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-[#252422]">{agent.name}</h3>
                      {agent.active !== false && hasUnsavedChanges(agent.id) && (
                        <span className="text-[9px] uppercase tracking-wider text-[#D45113] font-bold bg-[#D45113]/10 px-1.5 py-0.5 rounded animate-pulse">Unsaved</span>
                      )}
                    </div>
                    <Badge className="border-[#D8D4CC] bg-[#F5F2EB] text-[#44423E] font-semibold">{agent.model}</Badge>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => toggleAgentActive(agent.id)}
                      className="h-8 rounded-full text-xs text-[#44423E] hover:bg-[#44423E]/10 hover:text-black px-3 transition-colors font-semibold"
                      aria-label={`${agent.active !== false ? "Deactivate" : "Activate"} ${agent.name}`}
                    >
                      {agent.active !== false ? "Deactivate" : "Activate"}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => removeAgent(agent.id)}
                      className="h-8 rounded-full text-xs text-[#D45113] hover:bg-[#D45113]/10 hover:text-[#B33E0A] px-3 transition-colors font-semibold"
                      aria-label={`Remove ${agent.name}`}
                    >
                      Delete
                    </Button>
                  </div>
                </CardHeader>
 
                <CardContent className={cn("space-y-4 px-4 py-4 transition-all duration-200", agent.active === false && "opacity-50 grayscale pointer-events-none select-none")}>
 
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[10px] uppercase tracking-[0.3em] text-[#858076] font-semibold">Persona</p>
                      <p className="text-[10px] uppercase tracking-[0.28em] text-[#858076]/70">Markdown supported</p>
                    </div>
                    <Textarea
                      value={agent.persona}
                      onChange={(event) => updateAgent(agent.id, { persona: event.target.value })}
                      placeholder="Describe the agent's worldview, tone, and editing preferences."
                      className="min-h-[164px]"
                      disabled={agent.active === false}
                    />
                    <p className="text-xs leading-5 text-[#858076]">
                      Use Markdown for bullets, emphasis, and short sections. This keeps long personas readable.
                    </p>
                  </div>
 
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[10px] uppercase tracking-[0.3em] text-[#858076] font-semibold">Style References (2x5 Grid)</p>
                      <p className="text-[10px] uppercase tracking-[0.28em] text-[#858076]/70">Click a slot to upload</p>
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
                                ? "border-[#D8D4CC] bg-[#F5F2EB]/50"
                                : "border-dashed border-[#D8D4CC] hover:border-[#858076] hover:bg-[#F5F2EB]/40 bg-white"
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
                                    if (agent.active !== false) {
                                      handleClearStyle(agent.id, i);
                                    }
                                  }}
                                  disabled={agent.active === false}
                                  className="absolute inset-0 bg-black/70 opacity-0 group-hover:opacity-100 flex items-center justify-center text-[10px] uppercase tracking-wider text-[#F97316] font-bold transition-opacity disabled:cursor-not-allowed"
                                >
                                  Clear
                                </button>
                              </>
                            ) : (
                              <span className="text-[#858076] group-hover:text-[#252422] text-sm font-semibold">+</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
 
                  <div className="space-y-2">
                    <p className="text-[10px] uppercase tracking-[0.3em] text-[#858076] font-semibold">Model Selection & Save</p>
                    <div className="flex items-center gap-2">
                      <select
                        value={agent.model}
                        onChange={(event) => updateAgent(agent.id, { model: event.target.value as ModelName })}
                        className="flex-1 rounded-2xl border border-[#D8D4CC] bg-white px-3 py-2 text-sm text-[#252422] focus:border-[#858076] focus:text-[#252422] focus:outline-none disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed"
                        disabled={agent.active === false}
                      >
                        <option value="GPT-Image-2">GPT-Image-2</option>
                        <option value="Gemini-3-Pro">Gemini-3-Pro</option>
                        <option value="Midjourney">Midjourney</option>
                        <option value="Seedance-v2">Seedance-v2</option>
                      </select>
                      <Button
                        type="button"
                        onClick={() => saveAgent(agent.id)}
                        className="rounded-2xl border border-[#D8D4CC] bg-[#252422] px-4 text-[#FAF9F6] hover:bg-black hover:text-white disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed"
                        disabled={agent.active === false}
                      >
                        <Save className="mr-2 h-4 w-4" />
                        Save
                      </Button>
                      {savedStatus[agent.id] && (
                        <span className="text-xs font-semibold text-green-600 animate-in fade-in-50 duration-300">
                          Saved!
                        </span>
                      )}
                    </div>
                  </div>
 
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[10px] uppercase tracking-[0.3em] text-[#858076] font-semibold">Heartbeat</p>
                      <span className="text-xs text-[#252422] font-semibold">
                        {agent.heartbeatMinutes === 0 ? "disabled" : `${agent.heartbeatMinutes} times per day`}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={15}
                      step={1}
                      value={agent.heartbeatMinutes}
                      onChange={(event) => updateAgent(agent.id, { heartbeatMinutes: parseInt(event.target.value, 10) })}
                      className="h-2 w-full cursor-pointer appearance-none rounded-full bg-[#EFECE7] accent-[#252422] disabled:opacity-50 disabled:cursor-not-allowed"
                      disabled={agent.active === false}
                    />
                    <div className="flex justify-between text-[10px] uppercase tracking-[0.24em] text-[#858076]">
                      <span>none</span>
                      <span>15x/day</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </TabsContent>
 
          <TabsContent value="logs" className="outline-none">
            {status?.history && status.history.length > 0 ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b border-[#D8D4CC]/50 pb-2 mb-3">
                  <p className="text-[10px] uppercase tracking-[0.3em] text-[#858076] font-semibold">Pulse Status History</p>
                  <span className={cn(
                    "w-2.5 h-2.5 rounded-full",
                    status.active ? "bg-green-500 animate-pulse" : "bg-[#858076]/40"
                  )} />
                </div>
 
                <div className="space-y-2 max-h-[550px] overflow-y-auto pr-1">
                  {[...status.history].reverse().map((log, index) => {
                    const isError = log.message.toLowerCase().includes("error") || log.message.toLowerCase().includes("fail");
                    return (
                      <div
                        key={index}
                        className={cn(
                          "p-3 rounded-2xl border text-xs leading-relaxed transition-colors",
                          isError
                            ? "bg-[#FEF2F2] border-[#FCA5A5] text-[#991B1B]"
                            : log.active
                              ? "bg-[#F0FDF4] border-[#BBF7D0] text-[#166534]"
                              : "bg-white border-[#D8D4CC]/60 text-[#44423E]"
                        )}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1 border-b border-[#D8D4CC]/20 pb-1">
                          <span className="font-semibold uppercase tracking-[0.05em] text-[10px] text-[#252422]">
                            {log.agent_name || "System"}
                          </span>
                          <span className="text-[10px] text-[#858076]/80">
                            {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </span>
                        </div>
                        <p className="font-mono text-[10px] leading-relaxed whitespace-pre-wrap">{log.message}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 px-4 text-center border border-dashed border-[#D8D4CC] rounded-[1.5rem] bg-white">
                <p className="text-sm font-semibold text-[#44423E] mb-1">No logs available</p>
                <p className="text-xs text-[#858076] max-w-[280px]">
                  Trigger a manual Pulse or wait for the automatic heartbeat scheduler to see agent execution logs.
                </p>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
