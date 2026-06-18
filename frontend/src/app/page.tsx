"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { ManagementSidebar } from "@/components/management-sidebar";
import { SocialStudioFeed } from "@/components/social-studio-feed";
import { StudioStatusFooter } from "@/components/studio-status-footer";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { KnowledgeWeb } from "@/components/knowledge-web";
import { SocialStudioTable } from "@/components/social-studio-table";
import { InspirationManager } from "@/components/inspiration-manager";
import { ImageLightbox } from "@/components/image-lightbox";
import { fetchHistory, sortTurnsNewestFirst, type HistoryData } from "@/lib/history";
import { useStudioStatus } from "@/lib/useStudioStatus";

export default function Home() {
  const [unsavedAgentsList, setUnsavedAgentsList] = useState<string[]>([]);
  const [view, setView] = useState<"micro" | "macro" | "inspiration" | "table">("micro");
  const [history, setHistory] = useState<HistoryData | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const router = useRouter();

  const handleUnsavedChangeStateChange = useCallback((hasUnsaved: boolean, unsavedNames: string[]) => {
    setUnsavedAgentsList(unsavedNames);
  }, []);

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
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            <div className="lg:col-span-8">
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

            <div className="lg:col-span-4 bg-[#FAF9F6] border border-[#D8D4CC] rounded-3xl p-6 shadow-sm sticky top-8">
              <div className="flex flex-col space-y-4">
                <div>
                  <h2 className="text-xl font-bold font-display text-[#252422]">Agent Management</h2>
                  <p className="text-xs text-[#858076] mt-1">Adjust app behavior and review agent settings.</p>
                </div>
                <hr className="border-[#D8D4CC]" />
                <ManagementSidebar
                  onPulseStart={startPolling}
                  status={status}
                  onUnsavedChangeStateChange={handleUnsavedChangeStateChange}
                />
              </div>
            </div>
          </div>
        </div>
      </Tabs>

      <StudioStatusFooter status={status} />
      <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
    </main>
  );
}
