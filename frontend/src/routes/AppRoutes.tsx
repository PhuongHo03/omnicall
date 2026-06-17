import { useState } from "react";

import { AdminDashboardScreen } from "../features/admin/screens/AdminDashboardScreen";
import { AuthScreen } from "../features/auth/screens/AuthScreen";
import { useAuthSession } from "../features/auth/hooks/useAuthSession";
import { AppShell } from "../layouts/AppShell";
import { MeetingsScreen } from "../features/meetings/screens/MeetingsScreen";

export function AppRoutes() {
  const [currentView, setCurrentView] = useState<"meetings" | "admin">("meetings");
  const auth = useAuthSession();

  if (!auth.token || !auth.account) {
    return (
      <AuthScreen
        displayName={auth.displayName}
        email={auth.email}
        error={auth.error}
        isLoading={auth.isLoading}
        mode={auth.mode}
        password={auth.password}
        role={auth.role}
        onDisplayNameChange={auth.setDisplayName}
        onEmailChange={auth.setEmail}
        onModeChange={auth.setMode}
        onPasswordChange={auth.setPassword}
        onRoleChange={auth.setRole}
        onSubmit={auth.submit}
      />
    );
  }

  const safeView = auth.account.role === "Admin" ? currentView : "meetings";

  return (
    <AppShell account={auth.account} currentView={safeView} onLogout={auth.logout} onNavigate={setCurrentView}>
      {safeView === "admin" ? <AdminDashboardScreen token={auth.token} /> : <MeetingsScreen account={auth.account} token={auth.token} />}
    </AppShell>
  );
}
