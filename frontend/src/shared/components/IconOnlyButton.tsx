import type { ButtonHTMLAttributes, ReactNode } from "react";

type IconOnlyButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: ReactNode;
  label: string;
  variant?: "default" | "danger";
};

export function IconOnlyButton({ className, icon, label, type = "button", variant = "default", ...props }: IconOnlyButtonProps) {
  const variantClass = variant === "danger" ? " icon-only-button--danger" : "";
  const extraClass = className ? ` ${className}` : "";
  return (
    <button
      className={`icon-only-button${variantClass}${extraClass}`}
      title={label}
      aria-label={label}
      type={type}
      {...props}
    >
      {icon}
    </button>
  );
}
