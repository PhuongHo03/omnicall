import type { ReactNode } from "react";

type EmptyStateProps = {
  message: string;
  icon?: ReactNode;
  description?: string;
  className?: string;
};

export function EmptyState({ message, icon, description, className }: EmptyStateProps) {
  return (
    <div className={`empty-state${className ? ` ${className}` : ""}`}>
      {icon && <div className="empty-state__icon">{icon}</div>}
      <div className="empty-state__message">{message}</div>
      {description && <div className="empty-state__desc">{description}</div>}
    </div>
  );
}
