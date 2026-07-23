import { useCallback, useEffect, useMemo, useState } from "react";

import { usePollingEffect } from "../../../shared/hooks/usePollingEffect";
import { getAdminMetrics } from "../api/adminApi";
import type { AdminMetrics } from "../types/adminTypes";
import { useToast } from "../../../shared/layouts/ToastContext";

export function useAdminMetrics(token: string) {
  const { showToast } = useToast();
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshMetrics = useCallback(async (announce = false) => {
    setIsLoading(true);
    setError(null);
    try {
      const nextMetrics = await getAdminMetrics(token);
      setMetrics(nextMetrics);
      const message = nextMetrics.cache.hit ? "Metrics loaded from cache." : "Metrics refreshed.";
      setNotice(message);
      if (announce) showToast({ message, tone: "success" });
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Metrics request failed.";
      setError(message);
      if (announce) showToast({ message, tone: "error" });
    } finally {
      setIsLoading(false);
    }
  }, [showToast, token]);

  useEffect(() => {
    void refreshMetrics();
  }, [refreshMetrics]);

  usePollingEffect(() => void refreshMetrics(), 30000);

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
