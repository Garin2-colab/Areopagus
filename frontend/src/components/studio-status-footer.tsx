"use client";

import type { StudioStatus } from "@/lib/useStudioStatus";

type StudioStatusFooterProps = {
  status: StudioStatus | null;
};

export function StudioStatusFooter({ status }: StudioStatusFooterProps) {
  const agentLabel = status?.agent_name || "Studio";
  const message = status?.message || "Waiting for pulse.";

  return (
    <footer className="fixed inset-x-0 bottom-0 z-40 border-t border-zinc-700 bg-zinc-800/95 px-4 py-2 text-[10px] text-zinc-200 shadow-[0_-8px_24px_rgba(0,0,0,0.35)] backdrop-blur-sm">
      <div className="mx-auto flex max-w-7xl items-center gap-2 font-display tracking-[0.14em]">
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          <span
            className={`absolute inline-flex h-full w-full rounded-full ${
              status?.active ? "bg-emerald-400/60" : "bg-zinc-500/40"
            } blur-[2px]`}
          />
          <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${status?.active ? "bg-emerald-400" : "bg-zinc-500"}`} />
        </span>
        <span className="uppercase text-zinc-300">{agentLabel}</span>
        <span className="truncate text-zinc-400">{message}</span>
      </div>
    </footer>
  );
}
