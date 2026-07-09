import { useCallback, useEffect, useState } from "react";

import { usePollingEffect } from "../../../shared/hooks/usePollingEffect";
import { listMeetings } from "../../meetings/api/meetingApi";
import { clearAdminOperationalLogs, getAdminMeetingLogs } from "../api/adminApi";
import type { AdminMeetingLogSummary } from "../types/adminTypes";

export function useAdminMeetingLogs(token: string) {
  const [meetings, setMeetings] = useState<AdminMeetingLogSummary[]>([]);
  const [meetingNameMap, setMeetingNameMap] = useState<Map<string, string>>(new Map());
  const [isLoading, setIsLoading] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshMeetings = useCallback(
    async (silent = false) => {
      if (!silent) setIsLoading(true);
      setError(null);
      try {
        const [items, dbMeetings] = await Promise.all([
          getAdminMeetingLogs(token),
          listMeetings(token),
        ]);
        const names = new Map<string, string>();
        for (const m of dbMeetings) {
          names.set(m.id, m.title);
        }
        setMeetingNameMap(names);
        const merged = items.map((item) => ({
          ...item,
          meetingName: names.get(item.meetingId) || item.meetingName || item.meetingId.slice(0, 8),
        }));
        setMeetings(merged);
        if (!silent) setNotice(`Loaded ${items.length} meeting log groups.`);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Meeting logs request failed.");
      } finally {
        if (!silent) setIsLoading(false);
      }
    },
    [token]
  );

  useEffect(() => {
    void refreshMeetings();
  }, [refreshMeetings]);

  usePollingEffect(() => void refreshMeetings(true), 2000, autoRefresh);

  const clearAllLogs = useCallback(async () => {
    setIsClearing(true);
    setError(null);
    try {
      await clearAdminOperationalLogs(token);
      setMeetings([]);
      setNotice("All operational logs cleared.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Logs could not be cleared.");
    } finally {
      setIsClearing(false);
    }
  }, [token]);

  const filteredMeetings = search.trim()
    ? meetings.filter(
        (m) =>
          m.meetingId.includes(search.trim().toLowerCase()) ||
          (m.meetingName || "").toLowerCase().includes(search.trim().toLowerCase())
      )
    : meetings;

  return {
    autoRefresh,
    clearAllLogs,
    error,
    filteredMeetings,
    isClearing,
    isLoading,
    meetingNameMap,
    notice,
    refreshMeetings,
    search,
    setAutoRefresh,
    setSearch,
  };
}
