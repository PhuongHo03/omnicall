import { LogIn, UserPlus } from "lucide-react";

import type { AuthMode } from "../types/authTypes";

type AuthScreenProps = {
  confirmPassword: string;
  displayName: string;
  email: string;
  error: string | null;
  isLoading: boolean;
  mode: AuthMode;
  password: string;
  onConfirmPasswordChange: (value: string) => void;
  onDisplayNameChange: (value: string) => void;
  onEmailChange: (value: string) => void;
  onModeChange: (value: AuthMode) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: () => void;
};

export function AuthScreen({
  confirmPassword,
  displayName,
  email,
  error,
  isLoading,
  mode,
  onConfirmPasswordChange,
  onDisplayNameChange,
  onEmailChange,
  onModeChange,
  onPasswordChange,
  onSubmit,
  password
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
          {mode === "register" ? (
            <label>
              <span>Name</span>
              <input value={displayName} required disabled={isLoading} onChange={(event) => onDisplayNameChange(event.target.value)} />
            </label>
          ) : null}
          <label>
            <span>Email</span>
            <input value={email} type="email" pattern="^[^@\s]+@[^@\s]+\.[^@\s]+$" required disabled={isLoading} onChange={(event) => onEmailChange(event.target.value)} />
          </label>
          <label>
            <span>Password</span>
            <input value={password} type="password" required disabled={isLoading} onChange={(event) => onPasswordChange(event.target.value)} />
          </label>
          {mode === "register" ? (
            <label>
              <span>Confirm password</span>
              <input value={confirmPassword} type="password" required disabled={isLoading} onChange={(event) => onConfirmPasswordChange(event.target.value)} />
            </label>
          ) : null}
          <button
            className="icon-button icon-button--primary"
            disabled={isLoading || !email.trim() || !password || (mode === "register" && (!displayName.trim() || !confirmPassword))}
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
