import { useCallback, useEffect, useState } from "react";

import { getCurrentAccount, loginAccount, logoutAccount, registerAccount } from "../api/authApi";
import type { Account, AuthMode } from "../types/authTypes";

const TOKEN_KEY = "omnicall.sessionToken";

export function useAuthSession() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [account, setAccount] = useState<Account | null>(null);
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSessionChecking, setIsSessionChecking] = useState(Boolean(token));
  const [error, setError] = useState<string | null>(null);

  const persistSession = useCallback((nextToken: string, nextAccount: Account) => {
    localStorage.setItem(TOKEN_KEY, nextToken);
    setToken(nextToken);
    setAccount(nextAccount);
  }, []);

  const refreshAccount = useCallback(async () => {
    if (!token) {
      setAccount(null);
      setIsSessionChecking(false);
      return;
    }
    setIsSessionChecking(true);
    try {
      setAccount(await getCurrentAccount(token));
    } catch {
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setAccount(null);
    } finally {
      setIsSessionChecking(false);
    }
  }, [token]);

  useEffect(() => {
    void refreshAccount();
  }, [refreshAccount]);

  const submit = useCallback(() => {
    const validationError = validateAuthInput({ confirmPassword, displayName, email, mode, password });
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
            ? await registerAccount(email, password, displayName)
            : await loginAccount(email, password);
        persistSession(session.token, session.account);
        setIsSessionChecking(false);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Authentication failed.");
      } finally {
        setIsLoading(false);
      }
    })();
  }, [confirmPassword, displayName, email, mode, password, persistSession]);

  const logout = useCallback(() => {
    const currentToken = token;
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setAccount(null);
    setIsSessionChecking(false);
    if (currentToken) {
      void logoutAccount(currentToken);
    }
  }, [token]);

  return {
    account,
    confirmPassword,
    displayName,
    email,
    error,
    isLoading,
    isSessionChecking,
    mode,
    password,
    token,
    logout,
    setConfirmPassword,
    setDisplayName,
    setEmail,
    setMode,
    setPassword,
    submit
  };
}

function validateAuthInput({
  displayName,
  email,
  mode,
  password,
  confirmPassword
}: {
  confirmPassword: string;
  displayName: string;
  email: string;
  mode: AuthMode;
  password: string;
}): string | null {
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
    return "Email must use the format name@example.com.";
  }
  if (!password) {
    return "Password is required.";
  }
  if (mode === "register" && !displayName.trim()) {
    return "Name is required.";
  }
  if (mode === "register" && password !== confirmPassword) {
    return "Password confirmation does not match.";
  }
  return null;
}
