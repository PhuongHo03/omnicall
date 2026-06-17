import { LogIn, UserPlus } from "lucide-react";

import type { AuthMode } from "../types/authTypes";

type AuthScreenProps = {
  displayName: string;
  email: string;
  error: string | null;
  isLoading: boolean;
  mode: AuthMode;
  password: string;
  role: "Admin" | "User";
  onDisplayNameChange: (value: string) => void;
  onEmailChange: (value: string) => void;
  onModeChange: (value: AuthMode) => void;
  onPasswordChange: (value: string) => void;
  onRoleChange: (value: "Admin" | "User") => void;
  onSubmit: () => void;
};

export function AuthScreen({
  displayName,
  email,
  error,
  isLoading,
  mode,
  onDisplayNameChange,
  onEmailChange,
  onModeChange,
  onPasswordChange,
  onRoleChange,
  onSubmit,
  password,
  role
}: AuthScreenProps) {
  return (
    <main className="auth-screen">
      <section className="auth-panel-card">
        <div className="auth-brand">
          <strong>Omnicall</strong>
          <span>Sign in to manage meeting intelligence.</span>
        </div>
        <div className="auth-tabs">
          <button className={mode === "login" ? "auth-tab auth-tab--active" : "auth-tab"} type="button" onClick={() => onModeChange("login")}>
            <LogIn size={16} />
            Login
          </button>
          <button className={mode === "register" ? "auth-tab auth-tab--active" : "auth-tab"} type="button" onClick={() => onModeChange("register")}>
            <UserPlus size={16} />
            Register
          </button>
        </div>
        <form
          className="auth-form"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          <label>
            <span>Email</span>
            <input value={email} type="email" required disabled={isLoading} onChange={(event) => onEmailChange(event.target.value)} />
          </label>
          {mode === "register" ? (
            <>
              <label>
                <span>Name</span>
                <input value={displayName} required disabled={isLoading} onChange={(event) => onDisplayNameChange(event.target.value)} />
              </label>
              <label>
                <span>Role</span>
                <select value={role} disabled={isLoading} onChange={(event) => onRoleChange(event.target.value as "Admin" | "User")}>
                  <option value="Admin">Admin</option>
                  <option value="User">User</option>
                </select>
              </label>
            </>
          ) : null}
          <label>
            <span>Password</span>
            <input value={password} type="password" minLength={8} required disabled={isLoading} onChange={(event) => onPasswordChange(event.target.value)} />
          </label>
          <button
            className="icon-button icon-button--primary"
            disabled={isLoading || !email.trim() || !password || (mode === "register" && !displayName.trim())}
            type="submit"
          >
            {mode === "login" ? <LogIn size={16} /> : <UserPlus size={16} />}
            {mode === "login" ? "Login" : "Create account"}
          </button>
        </form>
        {error ? <div className="event-strip event-strip__error">{error}</div> : null}
      </section>
    </main>
  );
}
