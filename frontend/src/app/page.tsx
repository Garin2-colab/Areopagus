"use client";

import { forwardRef, useMemo, useRef, useState } from "react";
import { ArrowDown, Orbit } from "lucide-react";

import mockHistory from "../data/mock_history.json";
import { KnowledgeWeb } from "@/components/knowledge-web";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Turn = (typeof mockHistory.turns)[number];
type ViewMode = "micro" | "macro";

export default function Home() {
  const turns = useMemo(() => [...mockHistory.turns].sort((a, b) => a.turn - b.turn), []);
  const [view, setView] = useState<ViewMode>("micro");
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(turns[0]?.image_id ?? null);
  const stripRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const scrollToTurn = (turnId: string) => {
    setSelectedTurnId(turnId);
    setView("micro");
    requestAnimationFrame(() => {
      stripRefs.current[turnId]?.scrollIntoView({ behavior: "auto", block: "center" });
    });
  };

  return (
    <Tabs value={view} onValueChange={(value) => setView(value as ViewMode)}>
      <main className="min-h-screen bg-black text-zinc-50">
        <header className="sticky top-0 z-20 border-b border-zinc-800 bg-black/95 backdrop-blur-sm">
          <div className="mx-auto max-w-7xl px-6 py-6">
            <h1 className="text-[clamp(3.5rem,12vw,8rem)] font-semibold leading-none tracking-[-0.08em] text-white">
              AREOPAGUS
            </h1>
            <div className="mt-6 flex items-center gap-2">
              <TabsList className="rounded-none">
                <TabsTrigger value="micro" className="rounded-none">
                  <ArrowDown className="mr-2 h-3.5 w-3.5" />
                  Micro
                </TabsTrigger>
                <TabsTrigger value="macro" className="rounded-none">
                  <Orbit className="mr-2 h-3.5 w-3.5" />
                  Macro
                </TabsTrigger>
              </TabsList>
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-7xl px-6 pb-16">
          <TabsContent value="micro" className="mt-0">
            <section className="space-y-4">
              <h2 className="text-xl font-medium">Vertical strip view</h2>

              <div className="relative space-y-10 border border-zinc-800 bg-black px-4 py-8 md:px-8">
                <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-zinc-800" />
                {turns.map((turn, index) => (
                  <StripTurn
                    key={turn.turn}
                    ref={(node) => {
                      stripRefs.current[turn.image_id] = node;
                    }}
                    turn={turn}
                    index={index}
                    active={selectedTurnId === turn.image_id}
                    onImageClick={scrollToTurn}
                  />
                ))}
              </div>
            </section>
          </TabsContent>

          <TabsContent value="macro" className="mt-0">
            <h2 className="mb-4 text-xl font-medium">Knowledge web view</h2>
            <KnowledgeWeb turns={turns} onImageSelect={scrollToTurn} selectedTurnId={selectedTurnId} />
          </TabsContent>
        </div>

        <Separator />

        <footer className="mx-auto max-w-7xl px-6 py-8">
          <div className="flex flex-col gap-3 text-xs uppercase tracking-[0.28em] text-zinc-600 md:flex-row md:items-center md:justify-between">
            <span>Trace line</span>
          </div>
        </footer>
      </main>
    </Tabs>
  );
}

type StripTurnProps = {
  turn: Turn;
  index: number;
  active: boolean;
  onImageClick: (turnId: string) => void;
};

const StripTurn = forwardRef<HTMLDivElement, StripTurnProps>(({ turn, index, active, onImageClick }, ref) => {
  const isEven = index % 2 === 0;

  return (
    <article className="relative grid items-start gap-6 py-4 md:grid-cols-[1fr_minmax(320px,540px)_1fr]" ref={ref}>
      <div className={`${isEven ? "md:order-1" : "md:order-3"} space-y-3 md:pt-14`}>
        <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Agent 01</p>
        <div className="border border-zinc-800 bg-black p-4">
          <p className="text-sm leading-7 text-zinc-300">{turn.critique}</p>
        </div>
      </div>

      <div className="relative md:order-2">
        <button
          type="button"
          onClick={() => onImageClick(turn.image_id)}
          className={`block w-full border bg-black p-3 text-left ${active ? "border-zinc-300" : "border-zinc-800"}`}
          aria-label={`Jump to turn ${turn.turn}`}
        >
          <div className={`aspect-square border p-5 ${active ? "border-zinc-600 bg-zinc-950" : "border-zinc-800 bg-zinc-950"}`}>
            <div className="flex h-full flex-col justify-between">
              <div className="flex items-start justify-between gap-3 text-[10px] uppercase tracking-[0.28em] text-zinc-500">
                <span>Turn {turn.turn}</span>
                <span>{turn.image_id}</span>
              </div>

              <div className="space-y-4">
                <div className="space-y-2">
                  <p className="text-sm text-zinc-200">1080 x 1080 mock frame</p>
                  <p className="text-sm leading-6 text-zinc-500">{turn.image_url}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {turn.keywords.map((keyword) => (
                    <Badge key={keyword} className="border-zinc-700 text-zinc-300">
                      {keyword}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </button>

        <div className="absolute left-1/2 top-1/2 hidden h-px w-12 -translate-x-1/2 -translate-y-1/2 bg-zinc-700 md:block" />
      </div>

      <div className={`${isEven ? "md:order-3" : "md:order-1"} space-y-3 md:pt-14`}>
        <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Agent 02</p>
        <div className="border border-zinc-800 bg-black p-4">
          <p className="text-sm leading-7 text-zinc-300">Keywords: {turn.keywords.join(" · ")}</p>
        </div>
      </div>
    </article>
  );
});

StripTurn.displayName = "StripTurn";
