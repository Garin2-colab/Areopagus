"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Settings2, Lock } from "lucide-react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { ManagementSidebar } from "@/components/management-sidebar";
import { SocialStudioFeed } from "@/components/social-studio-feed";
import { StudioStatusFooter } from "@/components/studio-status-footer";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { KnowledgeWeb } from "@/components/knowledge-web";
import { SocialStudioTable } from "@/components/social-studio-table";
import { InspirationManager } from "@/components/inspiration-manager";
import { ImageLightbox } from "@/components/image-lightbox";
import { fetchHistory, sortTurnsNewestFirst, type HistoryData } from "@/lib/history";
import { useStudioStatus } from "@/lib/useStudioStatus";

export default function Home() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [unsavedAgentsList, setUnsavedAgentsList] = useState<string[]>([]);
  const [view, setView] = useState<"micro" | "macro" | "inspiration" | "table">("micro");
  const [pinInput, setPinInput] = useState("");
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [pinError, setPinError] = useState(false);

  const handleUnsavedChangeStateChange = useCallback((hasUnsaved: boolean, unsavedNames: string[]) => {
    setUnsavedAgentsList(unsavedNames);
  }, []);

  // Check localStorage on mount or when sheet opens
  useEffect(() => {
    if (typeof window !== "undefined") {
      const storedPin = localStorage.getItem("areopagus_admin_pin");
      const targetPin = process.env.NEXT_PUBLIC_ADMIN_PIN || "5995";
      if (storedPin === targetPin) {
        setIsAuthorized(true);
      } else {
        setIsAuthorized(false);
        setPinInput("");
        setPinError(false);
      }
    }
  }, [settingsOpen]);

  const handleVerifyPin = () => {
    const targetPin = process.env.NEXT_PUBLIC_ADMIN_PIN || "5995";
    if (pinInput === targetPin) {
      setIsAuthorized(true);
      setPinError(false);
      localStorage.setItem("areopagus_admin_pin", pinInput);
    } else {
      setPinError(true);
    }
  };
  const [history, setHistory] = useState<HistoryData | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const router = useRouter();

  const reloadHistory = async () => {
    try {
      // Clear Next.js and CDN edge caches
      await fetch("/api/revalidate", { method: "POST" }).catch(() => {});
      const data = await fetchHistory(true);
      setHistory(data);
      setHistoryError(null);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Failed to load history.");
    }
  };

  const { status, startPolling } = useStudioStatus({ onComplete: reloadHistory });

  useEffect(() => {
    let cancelled = false;
    fetchHistory(true)
      .then((data) => {
        if (cancelled) return;
        setHistory(data);
      })
      .catch((error) => {
        if (cancelled) return;
        setHistoryError(error instanceof Error ? error.message : "Failed to load history.");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const turns = useMemo(() => sortTurnsNewestFirst(history?.turns ?? []), [history]);
  const threads = useMemo(() => history?.threads ?? [], [history]);
  const inspiration = useMemo(() => history?.inspiration ?? [], [history]);

  return (
    <main className="min-h-screen bg-[#F5F2EB] pb-14 text-[#252422]">
      <Tabs value={view} onValueChange={(value) => setView(value as "micro" | "macro" | "inspiration" | "table")}>
        <header className="relative mx-auto max-w-7xl px-6 pt-8">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => setSettingsOpen(true)}
            aria-label="Open settings"
            className="absolute right-6 top-8 h-10 w-10 rounded-full border border-[#D8D4CC] bg-[#FAF9F6] text-[#44423E] hover:text-[#252422] hover:bg-[#F5F2EB] transition-colors"
          >
            <Settings2 className="h-4 w-4" />
          </Button>

          <div className="flex flex-col items-center gap-5">
            <div className="flex flex-col items-center gap-2">
              <h1 className="font-display text-5xl text-[#D45113] md:text-7xl">AREOPAGUS</h1>
            </div>

            <TabsList className="mx-auto">
              <TabsTrigger value="micro" className="px-4">
                Micro
              </TabsTrigger>
              <TabsTrigger value="macro" className="px-4">
                Macro
              </TabsTrigger>
              <TabsTrigger value="inspiration" className="px-4">
                Inspiration
              </TabsTrigger>
              <TabsTrigger value="table" className="px-4">
                Table
              </TabsTrigger>
            </TabsList>

            <div className="flex flex-col items-center gap-2 h-5">
              {view === "macro" && (
                <h2 className="font-display text-xs font-bold tracking-[0.25em] text-[#858076] uppercase">
                  Knowledge Web
                </h2>
              )}
              {view === "inspiration" && (
                <h2 className="font-display text-xs font-bold tracking-[0.25em] text-[#858076] uppercase">
                  Inspiration Board
                </h2>
              )}
              {view === "table" && (
                <h2 className="font-display text-xs font-bold tracking-[0.25em] text-[#858076] uppercase">
                  Database Table
                </h2>
              )}
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-7xl px-6 pb-10 pt-8">
          {historyError ? <p className="mb-4 text-sm text-zinc-400">{historyError}</p> : null}
          <div className={view === "micro" ? "mt-0 block animate-in fade-in-50 duration-200" : "hidden"}>
            <SocialStudioFeed turns={turns} threads={threads} onImageClick={setLightboxSrc} />
          </div>
          {view === "macro" && (
            <div className="mt-0 block animate-in fade-in-50 duration-200">
              <KnowledgeWeb
                turns={turns}
                threads={threads}
                inspiration={inspiration}
                onImageSelect={(id, kind) => {
                  if (kind === "inspiration") {
                    setView("inspiration");
                    setTimeout(() => {
                      const el = document.getElementById(`inspiration-${id}`);
                      if (el) {
                        el.scrollIntoView({ behavior: "smooth", block: "center" });
                        el.classList.add("ring-2", "ring-[#D45113]");
                        setTimeout(() => el.classList.remove("ring-2", "ring-[#D45113]"), 2000);
                      }
                    }, 150);
                  } else {
                    router.push(`/post/${id}`);
                  }
                }}
                selectedTurnId={null}
                activeNodes={status?.active_nodes ?? []}
                onRefresh={reloadHistory}
              />
            </div>
          )}
          <div className={view === "inspiration" ? "mt-0 block animate-in fade-in-50 duration-200" : "hidden"}>
            <InspirationManager
              inspiration={inspiration}
              onRefresh={reloadHistory}
              onImageClick={setLightboxSrc}
            />
          </div>
          <div className={view === "table" ? "mt-0 block animate-in fade-in-50 duration-200" : "hidden"}>
            <SocialStudioTable turns={turns} onRefresh={reloadHistory} onImageClick={setLightboxSrc} />
          </div>
        </div>
      </Tabs>

      <Sheet
        open={settingsOpen}
        onOpenChange={(open) => {
          if (!open && unsavedAgentsList.length > 0) {
            const agentNames = unsavedAgentsList.join(", ");
            const confirmClose = window.confirm(
              `You haven't saved the settings for: ${agentNames}.\nAre you sure you want to continue without saving?`
            );
            if (!confirmClose) {
              return;
            }
          }
          setSettingsOpen(open);
        }}
      >
        <SheetContent side="right" className="overflow-y-auto sm:max-w-[560px]">
          <SheetHeader className="mb-4 px-6 pt-6">
            <SheetTitle>Agent Management</SheetTitle>
            <SheetDescription>Adjust app behavior and review agent settings.</SheetDescription>
          </SheetHeader>
          {!isAuthorized ? (
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center space-y-6">
              <div className="w-12 h-12 rounded-full bg-[#D45113]/10 flex items-center justify-center text-[#D45113]">
                <Lock className="w-5 h-5" />
              </div>
              <div className="space-y-2">
                <h3 className="text-base font-semibold text-[#252422]">Access Code Required</h3>
                <p className="text-xs text-[#858076] max-w-[280px]">
                  Please enter the passcode to configure autonomous agents and trigger manual pulses.
                </p>
              </div>
              
              <div className="w-full max-w-[240px] space-y-4">
                <Input
                  type="password"
                  value={pinInput}
                  onChange={(e) => {
                    setPinError(false);
                    setPinInput(e.target.value);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      handleVerifyPin();
                    }
                  }}
                  className={cn(
                    "text-center text-lg tracking-[0.5em] font-semibold h-12 rounded-2xl border-[#D8D4CC] bg-white text-[#252422] focus:border-[#858076] focus:outline-none",
                    pinError && "border-red-500 focus:border-red-500 bg-red-50"
                  )}
                />
                
                {pinError && (
                  <p className="text-[11px] font-semibold text-red-600">Incorrect access code. Try again.</p>
                )}

                <Button
                  onClick={handleVerifyPin}
                  className="w-full h-11 rounded-full bg-[#252422] text-[#FAF9F6] hover:bg-black font-semibold text-xs transition-colors"
                >
                  Verify Access Code
                </Button>
              </div>
            </div>
          ) : (
            <div className="px-4 pb-6">
              <ManagementSidebar
                onPulseStart={startPolling}
                status={status}
                onUnsavedChangeStateChange={handleUnsavedChangeStateChange}
              />
            </div>
          )}
        </SheetContent>
      </Sheet>

      <StudioStatusFooter status={status} />
      <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
    </main>
  );
}
