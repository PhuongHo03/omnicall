import { useCallback, useEffect, useMemo, useState } from "react";

import { usePollingEffect } from "../../../shared/hooks/usePollingEffect";
import { clearAdminOperationalLogs, getAdminOperationalLogs } from "../api/adminApi";
import type { AdminLogFlow, AdminLogLevel, AdminOperationalLog } from "../types/adminTypes";
import { useToast } from "../../../shared/layouts/ToastContext";

export function useAdminLogs(token: string, meetingId?: string) {
  const { showToast } = useToast();
  const [logs, setLogs] = useState<AdminOperationalLog[]>([]);
  const [flow, setFlow] = useState<AdminLogFlow>("processing");
  const [level, setLevel] = useState<AdminLogLevel | "all">("all");
  const [limit, setLimit] = useState(100);
  const [search, setSearch] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [retainedLimit, setRetainedLimit] = useState(1000);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshLogs = useCallback(
    async (silent = false, announce = false) => {
      if (!silent) setIsLoading(true);
      setError(null);
      try {
        const response = await getAdminOperationalLogs(token, {
          flow,
          level,
          limit,
          search,
          meetingId,
        });
        setLogs(response.items);
        setRetainedLimit(response.retainedLimit);
        setSelectedEventId((current) => {
          if (current && response.items.some((event) => event.id === current)) {
            return current;
          }
          return response.items[0]?.id ?? null;
        });
        if (!silent) {
          const message = `Loaded ${response.items.length} ${flow === "rag" ? "RAG" : "processing"} events.`;
          setNotice(message);
          if (announce) showToast({ message, tone: "success" });
        }
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : "Operational logs request failed.";
        setError(message);
        if (announce) showToast({ message, tone: "error" });
      } finally {
        if (!silent) setIsLoading(false);
      }
    },
    [flow, level, limit, search, showToast, token, meetingId]
  );

  useEffect(() => {
    void refreshLogs();
  }, [refreshLogs]);

  usePollingEffect(() => void refreshLogs(true), 2000, autoRefresh);

  const clearLogs = useCallback(async () => {
    setIsClearing(true);
    setError(null);
    try {
      await clearAdminOperationalLogs(token, meetingId);
      setLogs([]);
      setSelectedEventId(null);
      setNotice(meetingId ? "Meeting logs cleared." : "Operational logs cleared.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Operational logs could not be cleared.");
    } finally {
      setIsClearing(false);
    }
  }, [token, meetingId]);

  const selectedEvent = useMemo(
    () => logs.find((event) => event.id === selectedEventId) ?? null,
    [logs, selectedEventId]
  );

  return {
    autoRefresh,
    clearLogs,
    error,
    flow,
    isClearing,
    isLoading,
    level,
    limit,
    logs,
    notice,
    refreshLogs,
    retainedLimit,
    selectedEvent,
    search,
    selectedEventId,
    setAutoRefresh,
    setFlow,
    setLevel,
    setLimit,
    setSearch,
    setSelectedEventId,
  };
}
