import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";
import { IconOnlyButton } from "./IconOnlyButton";

type DrawerProps = {
  isOpen: boolean;
  title: string;
  ariaLabel: string;
  children: ReactNode;
  onClose: () => void;
};

export function Drawer({ isOpen, title, ariaLabel, children, onClose }: DrawerProps) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-label={ariaLabel}
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="drawer__header">
          <h2>{title}</h2>
          <IconOnlyButton icon={<X size={18} />} label="Close" onClick={onClose} />
        </div>
        <div className="drawer__body">
          {children}
        </div>
      </aside>
    </div>
  );
}
