import type { ReactNode } from "react";
import { clsx } from "clsx";
import { AlertTriangle, Inbox } from "lucide-react";
import { ApiError } from "@/api/client";
import { useI18n } from "@/i18n/I18nProvider";
import { Button } from "./Button";
import { Disclosure } from "./Disclosure";

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-control bg-neutral-soft", className)} aria-hidden="true" />;
}

/** Rows of grey bars while a list loads, with the same height as the real rows (no layout jump). */
export function SkeletonList({ rows = 5, rowClassName = "h-16" }: { rows?: number; rowClassName?: string }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-2" role="status" aria-label={t("common.loading")}>
      {Array.from({ length: rows }, (_, index) => <Skeleton key={index} className={clsx("rounded-card", rowClassName)} />)}
    </div>
  );
}

export function EmptyState({ title, text, action, icon }: { title: string; text?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-card border border-dashed border-line bg-surface px-6 py-12 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
        {icon ?? <Inbox className="h-6 w-6" aria-hidden="true" />}
      </div>
      <p className="font-semibold text-ink">{title}</p>
      {text && <p className="mt-1 max-w-md text-sm text-muted">{text}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** A failed load: what happened in plain words, a retry, and the server's own message folded away. */
export function ErrorState({ error, onRetry, title }: { error: unknown; onRetry?: () => void; title?: string }) {
  const { t } = useI18n();
  const detail = error instanceof ApiError ? `${error.status || "—"} · ${error.detail}` : String(error);
  return (
    <div role="alert" className="rounded-card border border-danger/20 bg-danger-soft/60 px-5 py-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-ink">{title ?? t("error.load")}</p>
          <Disclosure label={t("common.technical_detail")} className="mt-1" compact>
            <p className="break-words text-xs text-muted">{detail}</p>
          </Disclosure>
        </div>
        {onRetry && <Button size="sm" onClick={onRetry}>{t("common.retry")}</Button>}
      </div>
    </div>
  );
}
