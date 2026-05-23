"use client";

import type { StudioStatus } from "@/lib/useStudioStatus";

type StudioStatusFooterProps = {
  status: StudioStatus | null;
};

export function StudioStatusFooter({ status }: StudioStatusFooterProps) {
  const agentLabel = status?.agent_name || "Studio";
  const message = status?.message || "Waiting for pulse.";

  return (
    <footer className="fixed inset-x-0 bottom-0 z-40 border-t border-[#D8D4CC] bg-[#FAF9F6]/90 px-4 py-2 text-[10px] text-[#44423E] shadow-sm backdrop-blur-sm">
      <div className="mx-auto flex max-w-7xl items-center gap-2 font-display tracking-[0.14em]">
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          <span
            className={`absolute inline-flex h-full w-full rounded-full ${
              status?.active ? "bg-emerald-500/60" : "bg-[#858076]/40"
            } blur-[2px]`}
          />
          <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${status?.active ? "bg-emerald-500" : "bg-[#858076]"}`} />
        </span>
        <span className="uppercase text-[#252422] font-semibold">{agentLabel}</span>
        <span className="truncate text-[#858076]">{message}</span>
      </div>
    </footer>
  );
}
