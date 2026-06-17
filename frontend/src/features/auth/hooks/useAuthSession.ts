import { useCallback, useEffect, useState } from "react";

import { getCurrentAccount, loginAccount, logoutAccount, registerAccount } from "../api/authApi";
import type { Account, AuthMode } from "../types/authTypes";

const TOKEN_KEY = "omnicall.sessionToken";

export function useAuthSession() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [account, setAccount] = useState<Account | null>(null);
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("admin@omnicall.local");
  const [password, setPassword] = useState("change-me-123");
  const [displayName, setDisplayName] = useState("Omnicall Admin");
  const [role, setRole] = useState<"Admin" | "User">("Admin");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const persistSession = useCallback((nextToken: string, nextAccount: Account) => {
    localStorage.setItem(TOKEN_KEY, nextToken);
    setToken(nextToken);
    setAccount(nextAccount);
  }, []);

  const refreshAccount = useCallback(async () => {
    if (!token) {
      setAccount(null);
      return;
    }
    try {
      setAccount(await getCurrentAccount(token));
    } catch {
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setAccount(null);
    }
  }, [token]);

  useEffect(() => {
    void refreshAccount();
  }, [refreshAccount]);

  const submit = useCallback(() => {
    const validationError = validateAuthInput({ displayName, email, mode, password });
    if (validationError) {
      setError(validationError);
      return;
    }
    setIsLoading(true);
    setError(null);
    void (async () => {
      try {
        const session =
          mode === "register"
            ? await registerAccount(email, password, displayName, role)
            : await loginAccount(email, password);
        persistSession(session.token, session.account);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Authentication failed.");
      } finally {
        setIsLoading(false);
      }
    })();
  }, [displayName, email, mode, password, persistSession, role]);

  const logout = useCallback(() => {
    const currentToken = token;
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setAccount(null);
    if (currentToken) {
      void logoutAccount(currentToken);
    }
  }, [token]);

  return {
    account,
    displayName,
    email,
    error,
    isLoading,
    mode,
    password,
    role,
    token,
    logout,
    setDisplayName,
    setEmail,
    setMode,
    setPassword,
    setRole,
    submit
  };
}

function validateAuthInput({
  displayName,
  email,
  mode,
  password
}: {
  displayName: string;
  email: string;
  mode: AuthMode;
  password: string;
}): string | null {
  if (!email.trim() || !email.includes("@")) {
    return "A valid email is required.";
  }
  if (password.length < 8) {
    return "Password must be at least 8 characters.";
  }
  if (mode === "register" && !displayName.trim()) {
    return "Name is required.";
  }
  return null;
}
