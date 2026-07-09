import { useEffect, useRef } from "react";

export function usePollingEffect(callback: () => void, intervalMs: number, enabled = true): void {
  const callbackRef = useRef(callback);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled) return;
    const interval = window.setInterval(() => callbackRef.current(), intervalMs);
    return () => window.clearInterval(interval);
  }, [enabled, intervalMs]);
}
