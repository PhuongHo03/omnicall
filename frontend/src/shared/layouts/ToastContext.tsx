import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ToastViewport } from "../components/ToastViewport";

export type AppToastTone = "success" | "error";

export type AppToast = {
  id: number;
  message: string;
  tone: AppToastTone;
  durationMs: number | null;
};

type ShowToastInput = {
  message: string;
  tone?: AppToastTone;
  durationMs?: number | null;
};

type ToastContextValue = {
  dismissToast: () => void;
  showToast: (input: ShowToastInput) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<AppToast | null>(null);
  const nextIdRef = useRef(0);

  const dismissToast = useCallback(() => setToast(null), []);
  const showToast = useCallback((input: ShowToastInput) => {
    nextIdRef.current += 1;
    setToast({
      id: nextIdRef.current,
      message: input.message,
      tone: input.tone ?? "success",
      durationMs: input.durationMs === undefined
        ? input.tone === "error" ? null : 4000
        : input.durationMs,
    });
  }, []);

  useEffect(() => {
    if (!toast || toast.durationMs === null) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setToast((current) => current?.id === toast.id ? null : current);
    }, toast.durationMs);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const value = useMemo(() => ({ dismissToast, showToast }), [dismissToast, showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toast={toast} onDismiss={dismissToast} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const value = useContext(ToastContext);
  if (!value) {
    throw new Error("useToast must be used within ToastProvider.");
  }
  return value;
}
