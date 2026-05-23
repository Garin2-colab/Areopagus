"use client";

import { useEffect, useRef, useState } from "react";

export type LogEntry = {
  message: string;
  active: boolean;
  timestamp: string;
  agent_name?: string;
};

export type StudioStatus = {
  message: string;
  active: boolean;
  updated_at: string;
  agent_name?: string;
  history?: LogEntry[];
};

const POLL_INTERVAL_MS = 3000;

async function fetchStudioStatus() {
  const response = await fetch("/api/status", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to fetch studio status: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as StudioStatus;
}

type UseStudioStatusOptions = {
  onComplete?: () => void | Promise<void>;
};

export function useStudioStatus({ onComplete }: UseStudioStatusOptions = {}) {
  const [status, setStatus] = useState<StudioStatus | null>(null);
  const inFlightRef = useRef(false);
  const sawActiveRef = useRef(false);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const pollOnce = async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;

    try {
      const nextStatus = await fetchStudioStatus();
      
      const wasActive = sawActiveRef.current;
      if (nextStatus.active) {
        sawActiveRef.current = true;
      } else {
        sawActiveRef.current = false;
      }

      setStatus(nextStatus);

      // Transition from active to inactive (Pulse completed)
      if (wasActive && !nextStatus.active) {
        await onCompleteRef.current?.();
      }
    } catch (err) {
      console.error("Failed to poll status:", err);
    } finally {
      inFlightRef.current = false;
    }
  };

  useEffect(() => {
    // Initial fetch
    void pollOnce();

    const interval = window.setInterval(() => {
      void pollOnce();
    }, POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(interval);
    };
  }, []);

  return {
    status,
    isPolling: status?.active ?? false,
    startPolling: pollOnce, // no-op fallback
    stopPolling: () => {},
    refresh: pollOnce
  };
}
