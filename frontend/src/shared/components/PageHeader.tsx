import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  subtitle?: ReactNode;
  children?: ReactNode;
};

export function PageHeader({ title, subtitle, children }: PageHeaderProps) {
  return (
    <section className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <span>{subtitle}</span>}
      </div>
      {children}
    </section>
  );
}
