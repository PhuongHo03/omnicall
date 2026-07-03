import type { ReactNode } from "react";

import { AlertTriangle, Trash2, X } from "lucide-react";
import { IconButton } from "./IconButton";

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
          <IconButton
            icon={<X size={16} />}
            label={cancelLabel}
            variant="secondary"
            type="button"
            onClick={onCancel}
          />
          <IconButton
            icon={<Trash2 size={16} />}
            label={confirmLabel}
            variant="danger"
            type="button"
            onClick={onConfirm}
          />
        </div>
      </section>
    </div>
  );
}
