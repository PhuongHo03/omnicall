import { useCallback, useEffect, useMemo, useState } from "react";

import { getAdminMetrics } from "../api/adminApi";
import type { AdminMetrics } from "../types/adminTypes";

export function useAdminDashboard(token: string) {
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshMetrics = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const nextMetrics = await getAdminMetrics(token);
      setMetrics(nextMetrics);
      setNotice(nextMetrics.cache.hit ? "Metrics loaded from cache." : "Metrics refreshed.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Metrics request failed.");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void refreshMetrics();
  }, [refreshMetrics]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void refreshMetrics();
    }, 30000);
    return () => window.clearInterval(interval);
  }, [refreshMetrics]);

  const groupedMetrics = useMemo(() => {
    const groups = new Map<string, AdminMetrics["metrics"]>();
    for (const metric of metrics?.metrics ?? []) {
      const current = groups.get(metric.category) ?? [];
      current.push(metric);
      groups.set(metric.category, current);
    }
    return Array.from(groups.entries()).map(([category, items]) => ({ category, items }));
  }, [metrics]);

  return {
    error,
    groupedMetrics,
    isLoading,
    metrics,
    notice,
    refreshMetrics
  };
}
