"use client";

import { useEffect, useRef, useState } from "react";

export type StudioStatus = {
  message: string;
  active: boolean;
  updated_at: string;
  agent_name?: string;
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
  const [isPolling, setIsPolling] = useState(false);
  const intervalRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const sawActiveRef = useRef(false);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
      }
    };
  }, []);

  const stopPolling = () => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPolling(false);
  };

  const pollOnce = async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;

    try {
      const nextStatus = await fetchStudioStatus();
      if (nextStatus.active) {
        sawActiveRef.current = true;
      }

      setStatus((current) => {
        if (
          current &&
          current.message === nextStatus.message &&
          current.active === nextStatus.active &&
          current.agent_name === nextStatus.agent_name
        ) {
          return current;
        }
        return nextStatus;
      });

      if (!nextStatus.active && sawActiveRef.current) {
        stopPolling();
        await onCompleteRef.current?.();
        return false;
      }

      return true;
    } catch {
      // Keep the last known status visible if one poll fails.
      return true;
    } finally {
      inFlightRef.current = false;
    }
  };

  const startPolling = async () => {
    stopPolling();
    sawActiveRef.current = false;
    setIsPolling(true);
    const shouldContinue = await pollOnce();
    if (!shouldContinue) {
      return;
    }

    intervalRef.current = window.setInterval(() => {
      void pollOnce();
    }, POLL_INTERVAL_MS);
  };

  return {
    status,
    isPolling,
    startPolling,
    stopPolling,
    refresh: pollOnce
  };
}
