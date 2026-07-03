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

export type AdminAccountRole = "Admin" | "User";

export type AdminAccount = {
  userId: string;
  email: string;
  displayName: string;
  role: AdminAccountRole;
  createdAt: string;
  canChangeRole: boolean;
};

export type AdminAccountList = {
  items: AdminAccount[];
};

export type AdminLogLevel = "info" | "error";
export type AdminLogFlow = "processing" | "rag";

export type AdminOperationalLog = {
  id: string;
  timestamp: string;
  level: AdminLogLevel;
  flow: AdminLogFlow;
  stage: string;
  status: string;
  message: string;
  workspaceId: string | null;
  meetingId: string | null;
  meetingName: string | null;
  file: Record<string, unknown>;
  chat: Record<string, unknown>;
  provider: string | null;
  model: string | null;
  durationMs: number | null;
  details: Record<string, unknown>;
  errorType: string | null;
  errorMessage: string | null;
};

export type AdminOperationalLogList = {
  items: AdminOperationalLog[];
  limit: number;
  retainedLimit: number;
};

export type AdminMeetingLogSummary = {
  meetingId: string;
  meetingName: string | null;
  processingCount: number;
  ragCount: number;
  latestTimestamp: string | null;
  latestLevel: string | null;
};
