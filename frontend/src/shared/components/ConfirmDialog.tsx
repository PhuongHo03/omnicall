import type { ReactNode } from "react";

import { AlertTriangle } from "lucide-react";

type ConfirmDialogProps = {
  cancelLabel?: string;
  children?: ReactNode;
  confirmLabel?: string;
  isOpen: boolean;
  message: string;
  title: string;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmDialog({
  cancelLabel = "Cancel",
  children,
  confirmLabel = "Delete",
  isOpen,
  message,
  onCancel,
  onConfirm,
  title
}: ConfirmDialogProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="confirm-dialog-backdrop" role="presentation">
      <section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
        <div className="confirm-dialog__icon" aria-hidden="true">
          <AlertTriangle size={22} />
        </div>
        <div className="confirm-dialog__body">
          <h2 id="confirm-dialog-title">{title}</h2>
          <p>{message}</p>
          {children}
        </div>
        <div className="confirm-dialog__actions">
          <button className="icon-button icon-button--secondary" type="button" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button className="icon-button icon-button--danger" type="button" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
