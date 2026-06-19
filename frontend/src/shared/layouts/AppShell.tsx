import { useEffect, useRef, useState, type ReactNode } from "react";
import { BarChart3, ChevronDown, ListTree, LogOut, RadioTower, ShieldCheck, UserRound, UsersRound } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";

import type { Account } from "../../features/auth/types/authTypes";

type AppShellProps = {
  children: ReactNode;
  account: Account;
  onLogout: () => void;
};

function navigationClass({ isActive }: { isActive: boolean }) {
  return isActive ? "topbar-nav__item topbar-nav__item--active" : "topbar-nav__item";
}

export function AppShell({ account, children, onLogout }: AppShellProps) {
  const location = useLocation();
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [isAdminMenuOpen, setIsAdminMenuOpen] = useState(false);
  const isAdminRoute = location.pathname.startsWith("/admin/");
  const AccountRoleIcon = account.role === "Admin" ? ShieldCheck : UserRound;

  useEffect(() => {
    setIsAdminMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!isAdminMenuOpen) {
      return;
    }
    const closeMenu = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setIsAdminMenuOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsAdminMenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", closeMenu);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeMenu);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isAdminMenuOpen]);

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
          <NavLink className={navigationClass} to="/meetings">
            <RadioTower size={16} />
            Meetings
          </NavLink>
        </nav>
        <div className="topbar-actions">
          {account.role === "Admin" ? (
            <div className="admin-portal-menu" ref={menuRef}>
              <button
                className={
                  isAdminRoute
                    ? "admin-portal-menu__trigger admin-portal-menu__trigger--active"
                    : "admin-portal-menu__trigger"
                }
                type="button"
                aria-expanded={isAdminMenuOpen}
                aria-haspopup="menu"
                onClick={() => setIsAdminMenuOpen((current) => !current)}
              >
                <ShieldCheck size={16} />
                <span>Admin Portal</span>
                <ChevronDown size={15} />
              </button>
              {isAdminMenuOpen ? (
                <div className="admin-portal-menu__popover" role="menu">
                  <NavLink
                    className={navigationClass}
                    role="menuitem"
                    to="/admin/metrics"
                    onClick={() => setIsAdminMenuOpen(false)}
                  >
                    <BarChart3 size={16} />
                    Metrics
                  </NavLink>
                  <NavLink
                    className={navigationClass}
                    role="menuitem"
                    to="/admin/accounts"
                    onClick={() => setIsAdminMenuOpen(false)}
                  >
                    <UsersRound size={16} />
                    Accounts
                  </NavLink>
                  <NavLink
                    className={navigationClass}
                    role="menuitem"
                    to="/admin/logs"
                    onClick={() => setIsAdminMenuOpen(false)}
                  >
                    <ListTree size={16} />
                    Logs
                  </NavLink>
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="account-menu">
            <button className="account-menu__trigger" type="button" aria-label="Account information">
              <AccountRoleIcon size={16} />
              <span>{account.displayName}</span>
              <ChevronDown size={14} />
            </button>
            <div className="account-menu__popover" role="status">
              <div className="account-menu__identity">
                <div className="account-menu__avatar" aria-hidden="true">
                  <AccountRoleIcon size={18} />
                </div>
                <div>
                  <strong>{account.displayName}</strong>
                  <span>{account.email}</span>
                </div>
              </div>
              <div className="account-menu__role">
                <span>Role</span>
                <strong>{account.role}</strong>
              </div>
            </div>
          </div>
          <button className="topbar-logout" type="button" onClick={onLogout} title="Logout">
            <LogOut size={16} />
          </button>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
