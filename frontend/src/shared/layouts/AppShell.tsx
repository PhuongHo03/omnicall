import { useEffect, useRef, useState, type ReactNode } from "react";
import { BarChart3, ListTree, LogOut, Moon, PanelLeftClose, PanelLeftOpen, Plus, RadioTower, ShieldCheck, Sun, UserRound, UsersRound } from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import type { Account } from "../../features/auth/types/authTypes";
import { IconOnlyButton } from "../components/IconOnlyButton";
import { useTheme } from "../hooks/useTheme";
import { useSidebarSlot } from "./SidebarContext";

type AppShellProps = {
  children: ReactNode;
  account: Account;
  onLogout: () => void;
};

export function AppShell({ account, children, onLogout }: AppShellProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { extraContent, onCreateMeeting } = useSidebarSlot();
  const { theme, toggleTheme } = useTheme();
  const AccountRoleIcon = account.role === "Admin" ? ShieldCheck : UserRound;
  const isMeetingsRoute = location.pathname.startsWith("/meetings");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    return localStorage.getItem("omnicall-sidebar-collapsed") === "true";
  });
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isBrandHovered, setIsBrandHovered] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isAdminSubmenuOpen, setIsAdminSubmenuOpen] = useState(false);
  const toggleSidebar = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("omnicall-sidebar-collapsed", String(next));
      return next;
    });
  };
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setIsUserMenuOpen(false);
    setIsAdminSubmenuOpen(false);
    setIsMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!isUserMenuOpen) return;
    const handleClickOutside = (e: PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsUserMenuOpen(false);
        setIsAdminSubmenuOpen(false);
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsUserMenuOpen(false);
        setIsAdminSubmenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("pointerdown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isUserMenuOpen]);



  return (
    <div className={`app-shell${isSidebarCollapsed ? " app-shell--sidebar-collapsed" : ""}`}>
      <aside className={`sidebar${isSidebarCollapsed ? " sidebar--collapsed" : ""}${isMobileOpen ? " open" : ""}`}>
        <div
          className="sidebar-brand"
          onMouseEnter={() => setIsBrandHovered(true)}
          onMouseLeave={() => setIsBrandHovered(false)}
        >
          {isSidebarCollapsed && isBrandHovered ? (
            <IconOnlyButton
              icon={<PanelLeftOpen size={16} />}
              label="Expand sidebar"
              onClick={toggleSidebar}
            />
          ) : (
            <div
              className="sidebar-brand-logo"
              role="button"
              tabIndex={0}
              onClick={() => navigate("/meetings")}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate("/meetings"); }}
            >
              <div className="sidebar-brand-icon">
                <RadioTower size={18} strokeWidth={2.4} />
              </div>
              <div className="sidebar-brand-text">Omnicall</div>
            </div>
          )}
          {!isSidebarCollapsed && (
            <IconOnlyButton
              icon={<PanelLeftClose size={16} />}
              label="Collapse sidebar"
              onClick={toggleSidebar}
            />
          )}
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {isMeetingsRoute && (
            <button
              className={`sidebar-item active${isSidebarCollapsed ? " sidebar-item--icon-only" : ""}`}
              type="button"
              onClick={() => onCreateMeeting?.()}
              title="New Meeting"
            >
              <Plus size={18} />
              {!isSidebarCollapsed && "New Meeting"}
            </button>
          )}

          {!isSidebarCollapsed && isMeetingsRoute && extraContent}
        </nav>

        <div className="sidebar-user-wrapper" ref={menuRef}>
          {isUserMenuOpen && (
            <div className="sidebar-user-menu">
              <div className="sidebar-user-menu__identity">
                <div className="sidebar-user-menu__avatar">
                  <AccountRoleIcon size={18} />
                </div>
                <div>
                  <div className="sidebar-user-menu__name">{account.displayName}</div>
                  <div className="sidebar-user-menu__email">{account.email}</div>
                </div>
              </div>

              <div className="sidebar-user-menu__divider" />

              <button className="sidebar-user-menu__item" type="button" onClick={toggleTheme}>
                {theme === "light" ? <Moon size={15} /> : <Sun size={15} />}
                <span>{theme === "light" ? "Dark" : "Light"} mode</span>
              </button>

              {account.role === "Admin" && (
                <div
                  className="sidebar-user-menu__admin-wrap"
                  onMouseEnter={() => setIsAdminSubmenuOpen(true)}
                  onMouseLeave={() => setIsAdminSubmenuOpen(false)}
                >
                  <button
                    className="sidebar-user-menu__item"
                    type="button"
                    onClick={() => navigate("/admin")}
                  >
                    <ShieldCheck size={15} />
                    <span>Admin</span>
                    <span className="sidebar-user-menu__arrow">▸</span>
                  </button>
                  {isAdminSubmenuOpen && (
                    <div className="sidebar-user-menu__admin-submenu">
                      <NavLink to="/admin/metrics" className="sidebar-user-menu__admin-item">
                        <BarChart3 size={15} />
                        Metrics
                      </NavLink>
                      <NavLink to="/admin/accounts" className="sidebar-user-menu__admin-item">
                        <UsersRound size={15} />
                        Accounts
                      </NavLink>
                      <NavLink to="/admin/logs" className="sidebar-user-menu__admin-item">
                        <ListTree size={15} />
                        Logs
                      </NavLink>
                    </div>
                  )}
                </div>
              )}

              <div className="sidebar-user-menu__divider" />

              <button className="sidebar-user-menu__item sidebar-user-menu__item--danger" type="button" onClick={onLogout}>
                <LogOut size={15} />
                <span>Logout</span>
              </button>
            </div>
          )}



          <button
            className={`sidebar-user${isSidebarCollapsed ? " sidebar-user--collapsed" : ""}`}
            type="button"
            onClick={() => setIsUserMenuOpen((c) => !c)}
          >
            <div className="sidebar-user-avatar">
              <AccountRoleIcon size={16} />
            </div>
            {!isSidebarCollapsed && (
              <div className="sidebar-user-info">
                <div className="sidebar-user-name">{account.displayName}</div>
                <div className="sidebar-user-email">{account.email}</div>
              </div>
            )}
          </button>
        </div>
      </aside>
      <div className="sidebar-overlay" onClick={() => setIsMobileOpen(false)} />
      <main className="main-content">
        <div className="mobile-header">
          <IconOnlyButton icon={<PanelLeftOpen size={18} />} label="Open sidebar" onClick={() => setIsMobileOpen(true)} />
          <span className="mobile-header__title">Omnicall</span>
        </div>
        {children}
      </main>
    </div>
  );
}
