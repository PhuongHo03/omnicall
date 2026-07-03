import { ArrowLeft, BarChart3, ListTree, UsersRound } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";

import { IconOnlyButton } from "../../../shared/components/IconOnlyButton";

export function AdminNavbar() {
  const navigate = useNavigate();

  return (
    <nav className="admin-navbar">
      <IconOnlyButton
        icon={<ArrowLeft size={16} />}
        label="Back"
        onClick={() => navigate(-1)}
      />
      <div className="admin-navbar__tabs">
        <NavLink to="/admin/metrics" className={({ isActive }) => `admin-navbar__tab${isActive ? " admin-navbar__tab--active" : ""}`}>
          <BarChart3 size={15} />
          <span>Metrics</span>
        </NavLink>
        <NavLink to="/admin/accounts" className={({ isActive }) => `admin-navbar__tab${isActive ? " admin-navbar__tab--active" : ""}`}>
          <UsersRound size={15} />
          <span>Accounts</span>
        </NavLink>
        <NavLink to="/admin/logs" className={({ isActive }) => `admin-navbar__tab${isActive ? " admin-navbar__tab--active" : ""}`}>
          <ListTree size={15} />
          <span>Logs</span>
        </NavLink>
      </div>
      <div className="admin-navbar__spacer" />
    </nav>
  );
}
