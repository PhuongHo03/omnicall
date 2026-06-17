export type AdminMetricSeries = {
  labels: Record<string, string>;
  value: number | null;
};

export type AdminMetric = {
  name: string;
  label: string;
  category: string;
  unit: string;
  query: string;
  status: "ok" | "no_data" | "unavailable";
  series: AdminMetricSeries[];
};

export type AdminMetricsTarget = {
  job: string;
  instance: string;
  health: string;
  scrapeUrl: string;
  lastScrape: string | null;
  lastError: string;
};

export type AdminMetrics = {
  generatedAt: string;
  cache: {
    hit: boolean;
    key: string;
    ttlSeconds: number;
  };
  summary: {
    status: string;
    healthyTargets: number;
    totalTargets: number;
    degradedTargets: number;
  };
  targets: AdminMetricsTarget[];
  metrics: AdminMetric[];
};

export type AdminAuthContext = {
  userId: string;
  workspaceId: string;
  userEmail: string;
  userName: string;
  workspaceName: string;
};
