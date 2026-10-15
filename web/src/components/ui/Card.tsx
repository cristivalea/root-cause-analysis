import type { HTMLAttributes, ReactNode } from "react";
import { clsx } from "clsx";

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("rounded-card border border-line bg-surface shadow-card", className)} {...rest} />;
}

export function CardHeader({ title, subtitle, action, className }: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

/** A page title with one short subtitle and, optionally, the page's main action. */
export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-[15px] text-muted">{subtitle}</p>}
      </div>
      {action}
    </header>
  );
}

/** An id as people read it: PRB-2026-00012, INC-…, RCA-… */
export function Id({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={clsx("tabular whitespace-nowrap text-[13px] font-medium text-muted", className)}>{children}</span>;
}
