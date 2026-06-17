import type { ReactNode } from "react";
import { Activity, BarChart3, LogOut, RadioTower } from "lucide-react";
import type { Account } from "../features/auth/types/authTypes";

type AppShellProps = {
  children: ReactNode;
  currentView: "meetings" | "admin";
  account: Account;
  onNavigate: (view: "meetings" | "admin") => void;
  onLogout: () => void;
};

export function AppShell({ account, children, currentView, onLogout, onNavigate }: AppShellProps) {
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
        <nav className="topbar-nav" aria-label="Primary">
          <button
            className={currentView === "meetings" ? "topbar-nav__item topbar-nav__item--active" : "topbar-nav__item"}
            type="button"
            onClick={() => onNavigate("meetings")}
          >
            <RadioTower size={16} />
            Meetings
          </button>
          {account.role === "Admin" ? (
            <button
              className={currentView === "admin" ? "topbar-nav__item topbar-nav__item--active" : "topbar-nav__item"}
              type="button"
              onClick={() => onNavigate("admin")}
            >
              <BarChart3 size={16} />
              Dashboard
            </button>
          ) : null}
        </nav>
        <div className="runtime-chip">
          <Activity size={16} />
          <span>{account.role}</span>
        </div>
        <button className="topbar-logout" type="button" onClick={onLogout} title="Logout">
          <LogOut size={16} />
        </button>
      </header>
      <main>{children}</main>
    </div>
  );
}
