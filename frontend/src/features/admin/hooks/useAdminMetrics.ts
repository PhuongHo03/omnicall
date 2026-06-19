import { useCallback, useEffect, useMemo, useState } from "react";

import { getAdminMetrics } from "../api/adminApi";
import type { AdminMetrics } from "../types/adminTypes";

export function useAdminMetrics(token: string) {
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
      const category = combinedMetricsCategory(metric.category);
      const current = groups.get(category) ?? [];
      current.push(metric);
      groups.set(category, current);
    }
    return Array.from(groups.entries())
      .map(([category, items]) => ({ category, items }))
      .sort((left, right) => categoryOrder(left.category) - categoryOrder(right.category));
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

function combinedMetricsCategory(category: string) {
  if (category === "application" || category === "worker") {
    return "Meeting Operations";
  }
  if (["database", "cache", "queue", "storage", "vector", "gateway"].includes(category)) {
    return "Infrastructure Services";
  }
  if (category === "backend") {
    return "Backend";
  }
  if (category === "containers") {
    return "Containers";
  }
  return category;
}

function categoryOrder(category: string) {
  const order: Record<string, number> = {
    "Meeting Operations": 0,
    Backend: 1,
    Containers: 2,
    "Infrastructure Services": 3
  };
  return order[category] ?? 99;
}
