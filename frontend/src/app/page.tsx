"use client";

import { useEffect, useMemo, useState } from "react";
import { Settings2 } from "lucide-react";
import { useRouter } from "next/navigation";

import { ManagementSidebar } from "@/components/management-sidebar";
import { SocialStudioFeed } from "@/components/social-studio-feed";
import { StudioStatusFooter } from "@/components/studio-status-footer";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { KnowledgeWeb } from "@/components/knowledge-web";
import { SocialStudioTable } from "@/components/social-studio-table";
import { ImageLightbox } from "@/components/image-lightbox";
import { fetchHistory, sortTurnsNewestFirst, type HistoryData } from "@/lib/history";
import { useStudioStatus } from "@/lib/useStudioStatus";

export default function Home() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [view, setView] = useState<"micro" | "macro" | "table">("micro");
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
    fetchHistory()
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

  return (
    <main className="min-h-screen bg-[#F5F2EB] pb-14 text-[#252422]">
      <Tabs value={view} onValueChange={(value) => setView(value as "micro" | "macro" | "table")}>
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
              <h1 className="font-display text-5xl font-extrabold tracking-tighter text-[#252422] md:text-7xl">AREOPAGUS</h1>
              {view === "macro" && (
                <h2 className="font-display text-xs font-bold tracking-[0.25em] text-[#858076] uppercase">
                  Knowledge Web
                </h2>
              )}
              {view === "table" && (
                <h2 className="font-display text-xs font-bold tracking-[0.25em] text-[#858076] uppercase">
                  Database Table
                </h2>
              )}
            </div>

            <TabsList className="mx-auto">
              <TabsTrigger value="micro" className="px-4">
                Micro
              </TabsTrigger>
              <TabsTrigger value="macro" className="px-4">
                Macro
              </TabsTrigger>
              <TabsTrigger value="table" className="px-4">
                Table
              </TabsTrigger>
            </TabsList>
          </div>
        </header>

        <div className="mx-auto max-w-7xl px-6 pb-10 pt-8">
          {historyError ? <p className="mb-4 text-sm text-zinc-400">{historyError}</p> : null}
          <TabsContent value="micro" className="mt-0">
            <SocialStudioFeed turns={turns} threads={threads} onImageClick={setLightboxSrc} />
          </TabsContent>
          <TabsContent value="macro" className="mt-0">
            <KnowledgeWeb
              turns={turns}
              threads={threads}
              onImageSelect={(turnId) => router.push(`/post/${turnId}` as any)}
              selectedTurnId={null}
              resetToken={0}
            />
          </TabsContent>
          <TabsContent value="table" className="mt-0">
            <SocialStudioTable turns={turns} onRefresh={reloadHistory} onImageClick={setLightboxSrc} />
          </TabsContent>
        </div>
      </Tabs>

      <Sheet open={settingsOpen} onOpenChange={setSettingsOpen}>
        <SheetContent side="right" className="overflow-y-auto sm:max-w-[560px]">
          <SheetHeader className="mb-4 px-6 pt-6">
            <SheetTitle>Agent Management</SheetTitle>
            <SheetDescription>Adjust app behavior and review agent settings.</SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-6">
            <ManagementSidebar onPulseStart={startPolling} />
          </div>
        </SheetContent>
      </Sheet>

      <StudioStatusFooter status={status} />
      <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
    </main>
  );
}
