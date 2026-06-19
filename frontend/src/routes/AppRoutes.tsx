import { useCallback } from "react";
import { Navigate, Outlet, Route, Routes, useNavigate, useParams } from "react-router-dom";

import { AdminAccountsScreen } from "../features/admin/screens/AdminAccountsScreen";
import { AdminMetricsScreen } from "../features/admin/screens/AdminMetricsScreen";
import { AdminLogsScreen } from "../features/admin/screens/AdminLogsScreen";
import { AuthScreen } from "../features/auth/screens/AuthScreen";
import { useAuthSession } from "../features/auth/hooks/useAuthSession";
import type { Account } from "../features/auth/types/authTypes";
import { MeetingsScreen } from "../features/meetings/screens/MeetingsScreen";
import { AppShell } from "../shared/layouts/AppShell";

type AuthState = ReturnType<typeof useAuthSession>;

export function AppRoutes() {
  const auth = useAuthSession();

  if (auth.isSessionChecking) {
    return <RouteLoading />;
  }

  return (
    <Routes>
      <Route path="/auth" element={<GuestRoute auth={auth} />} />
      <Route element={<AuthenticatedLayout auth={auth} />}>
        <Route path="/meetings" element={<MeetingsRoute auth={auth} />} />
        <Route path="/meetings/:meetingId" element={<MeetingsRoute auth={auth} />} />
        <Route element={<AdminRoute account={auth.account} />}>
          <Route path="/admin" element={<Navigate to="/admin/metrics" replace />} />
          <Route path="/admin/metrics" element={<AdminMetricsScreen token={auth.token as string} />} />
          <Route path="/admin/accounts" element={<AdminAccountsScreen token={auth.token as string} />} />
          <Route path="/admin/logs" element={<AdminLogsScreen token={auth.token as string} />} />
        </Route>
      </Route>
      <Route path="/" element={<Navigate to={auth.account ? "/meetings" : "/auth"} replace />} />
      <Route path="*" element={<Navigate to={auth.account ? "/meetings" : "/auth"} replace />} />
    </Routes>
  );
}

function GuestRoute({ auth }: { auth: AuthState }) {
  if (auth.account && auth.token) {
    return <Navigate to="/meetings" replace />;
  }
  return (
    <AuthScreen
      confirmPassword={auth.confirmPassword}
      displayName={auth.displayName}
      email={auth.email}
      error={auth.error}
      isLoading={auth.isLoading}
      mode={auth.mode}
      password={auth.password}
      onConfirmPasswordChange={auth.setConfirmPassword}
      onDisplayNameChange={auth.setDisplayName}
      onEmailChange={auth.setEmail}
      onModeChange={auth.setMode}
      onPasswordChange={auth.setPassword}
      onSubmit={auth.submit}
    />
  );
}

function AuthenticatedLayout({ auth }: { auth: AuthState }) {
  if (!auth.account || !auth.token) {
    return <Navigate to="/auth" replace />;
  }
  return (
    <AppShell account={auth.account} onLogout={auth.logout}>
      <Outlet />
    </AppShell>
  );
}

function AdminRoute({ account }: { account: Account | null }) {
  if (account?.role !== "Admin") {
    return <Navigate to="/meetings" replace />;
  }
  return <Outlet />;
}

function MeetingsRoute({ auth }: { auth: AuthState }) {
  const { meetingId } = useParams();
  const navigate = useNavigate();
  const handleSelectedMeetingChange = useCallback(
    (selectedMeetingId: string | null) => {
      navigate(selectedMeetingId ? `/meetings/${selectedMeetingId}` : "/meetings");
    },
    [navigate]
  );
  if (!auth.account || !auth.token) {
    return <Navigate to="/auth" replace />;
  }
  return (
    <MeetingsScreen
      account={auth.account}
      token={auth.token}
      requestedMeetingId={meetingId ?? null}
      onSelectedMeetingChange={handleSelectedMeetingChange}
    />
  );
}

function RouteLoading() {
  return (
    <main className="auth-screen">
      <section className="auth-panel-card">
        <div className="auth-brand">
          <strong>Omnicall</strong>
          <span>Restoring your session.</span>
        </div>
      </section>
    </main>
  );
}
