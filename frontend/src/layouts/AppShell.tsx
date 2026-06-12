import type { ReactNode } from "react";
import { Activity, RadioTower } from "lucide-react";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">
          <RadioTower size={22} strokeWidth={2.4} />
        </div>
        <div className="brand-copy">
          <strong>Omnicall</strong>
          <span>Meeting intelligence console</span>
        </div>
        <div className="runtime-chip">
          <Activity size={16} />
          <span>Local</span>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
