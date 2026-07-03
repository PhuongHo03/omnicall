import type { ButtonHTMLAttributes, ReactNode } from "react";

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: ReactNode;
  label: string;
  variant?: "primary" | "secondary" | "danger";
};

export function IconButton({ icon, label, variant = "secondary", ...props }: IconButtonProps) {
  return (
    <button className={`icon-button icon-button--${variant}`} title={label} aria-label={label} {...props}>
      {icon}
      <span>{label}</span>
    </button>
  );
}
