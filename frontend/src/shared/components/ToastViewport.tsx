import { AlertCircle, CheckCircle2, X } from "lucide-react";

import type { AppToast } from "../layouts/ToastContext";

type ToastViewportProps = {
  toast: AppToast | null;
  onDismiss: () => void;
};

export function ToastViewport({ toast, onDismiss }: ToastViewportProps) {
  if (!toast) {
    return null;
  }

  const Icon = toast.tone === "error" ? AlertCircle : CheckCircle2;

  return (
    <div className="global-toast-viewport" aria-live={toast.tone === "error" ? "assertive" : "polite"}>
      <div
        className={`global-toast global-toast--${toast.tone}`}
        role={toast.tone === "error" ? "alert" : "status"}
        aria-atomic="true"
      >
        <Icon aria-hidden="true" size={18} strokeWidth={2.25} />
        <span>{toast.message}</span>
        <button type="button" className="global-toast__dismiss" aria-label="Dismiss notification" onClick={onDismiss}>
          <X aria-hidden="true" size={16} />
        </button>
      </div>
    </div>
  );
}
