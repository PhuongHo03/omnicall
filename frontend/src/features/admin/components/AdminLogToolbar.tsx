import { ListEnd, Radio, RefreshCw, Search, Trash2 } from "lucide-react";

import { IconButton } from "../../../shared/components/IconButton";
import type { AdminLogFlow, AdminLogLevel } from "../types/adminTypes";

type AdminLogToolbarMode = "list" | "detail";

type AdminLogToolbarProps = {
  mode: AdminLogToolbarMode;
  autoRefresh: boolean;
  isClearing: boolean;
  isLoading: boolean;
  onAutoRefreshChange: (value: boolean) => void;
  onClear: () => void;
  onRefresh: () => void;
  flow?: AdminLogFlow;
  level?: AdminLogLevel | "all";
  limit?: number;
  search?: string;
  onFlowChange?: (value: AdminLogFlow) => void;
  onLevelChange?: (value: AdminLogLevel | "all") => void;
  onLimitChange?: (value: number) => void;
  onSearchChange?: (value: string) => void;
};

export function AdminLogToolbar({
  mode,
  autoRefresh,
  isClearing,
  isLoading,
  onAutoRefreshChange,
  onClear,
  onRefresh,
  flow,
  level,
  limit,
  search,
  onFlowChange,
  onLevelChange,
  onLimitChange,
  onSearchChange,
}: AdminLogToolbarProps) {
  return (
    <section className="admin-log-toolbar" aria-label="Operational log controls">
      {mode === "detail" && flow && onFlowChange && (
        <div className="admin-log-tabs" role="tablist" aria-label="Log flow">
          <button
            className={flow === "processing" ? "admin-log-tabs__item admin-log-tabs__item--active" : "admin-log-tabs__item"}
            type="button"
            role="tab"
            aria-selected={flow === "processing"}
            onClick={() => onFlowChange("processing")}
          >
            Processing Logs
          </button>
          <button
            className={flow === "rag" ? "admin-log-tabs__item admin-log-tabs__item--active" : "admin-log-tabs__item"}
            type="button"
            role="tab"
            aria-selected={flow === "rag"}
            onClick={() => onFlowChange("rag")}
          >
            RAG Chat Logs
          </button>
        </div>
      )}

      {search !== undefined && onSearchChange && (
        <div className="admin-log-search">
          <Search size={16} />
          <input
            type="search"
            aria-label="Search operational logs"
            value={search}
            placeholder="Search session, file, provider, model..."
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>
      )}

      {mode === "detail" && level && onLevelChange && (
        <div className="admin-log-levels" aria-label="Log level">
          {(["all", "info", "error"] as const).map((value) => (
            <button
              className={level === value ? "admin-log-levels__item admin-log-levels__item--active" : "admin-log-levels__item"}
              key={value}
              type="button"
              onClick={() => onLevelChange(value)}
            >
              {value === "all" ? "All" : value === "info" ? "Info" : "Error"}
            </button>
          ))}
        </div>
      )}

      {mode === "detail" && limit !== undefined && onLimitChange && (
        <div className="admin-log-tail">
          <ListEnd size={15} />
          <span>Tail</span>
          <select
            aria-label="Number of recent log events"
            value={limit}
            onChange={(event) => onLimitChange(Number(event.target.value))}
          >
            <option value={100}>100</option>
            <option value={300}>300</option>
            <option value={1000}>1000</option>
          </select>
        </div>
      )}

      <div className="admin-log-toolbar__spacer" />

      <button
        className={autoRefresh ? "admin-log-live admin-log-live--active" : "admin-log-live"}
        type="button"
        aria-pressed={autoRefresh}
        title={autoRefresh ? "Pause live refresh" : "Resume live refresh"}
        onClick={() => onAutoRefreshChange(!autoRefresh)}
      >
        <Radio size={15} />
        <span>Live</span>
      </button>

      <IconButton
        icon={<RefreshCw size={16} />}
        label="Refresh"
        disabled={isLoading}
        type="button"
        onClick={onRefresh}
      />
      <IconButton
        icon={<Trash2 size={16} />}
        label="Clear"
        disabled={isClearing}
        type="button"
        onClick={onClear}
        variant="danger"
      />
    </section>
  );
}
