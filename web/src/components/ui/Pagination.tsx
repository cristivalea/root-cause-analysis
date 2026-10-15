import { clsx } from "clsx";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

/** The page numbers to show: always the first, the last and the neighbours of the current page. */
export function pageItems(page: number, pages: number): (number | "gap")[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1);
  const shown = new Set([1, pages, page - 1, page, page + 1].filter((item) => item >= 1 && item <= pages));
  const sorted = [...shown].sort((a, b) => a - b);
  const items: (number | "gap")[] = [];
  sorted.forEach((item, index) => {
    const previous = sorted[index - 1];
    if (previous !== undefined && item - previous > 1) items.push("gap");
    items.push(item);
  });
  return items;
}

export function Pagination({ page, pageSize, total, onPageChange, pageSizes, onPageSizeChange }: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  pageSizes?: number[];
  onPageSizeChange?: (size: number) => void;
}) {
  const { t } = useI18n();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  const arrow = "inline-flex h-8 w-8 items-center justify-center rounded-control text-muted hover:bg-brand-50 hover:text-ink disabled:pointer-events-none disabled:opacity-40";

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
      <div className="flex items-center gap-3 text-muted">
        <span className="tabular">{t("pagination.range", { from, to, total })}</span>
        {pageSizes && onPageSizeChange && (
          <label className="flex items-center gap-2">
            <span>{t("pagination.per_page")}</span>
            <select
              value={pageSize}
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
              className="h-8 cursor-pointer rounded-control border border-line bg-surface px-2 text-ink"
            >
              {pageSizes.map((size) => <option key={size} value={size}>{size}</option>)}
            </select>
          </label>
        )}
      </div>
      {pages > 1 && (
        <nav aria-label={t("pagination.label")} className="flex items-center gap-1">
          <button type="button" className={arrow} onClick={() => onPageChange(page - 1)} disabled={page <= 1}
                  aria-label={t("pagination.previous")}>
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          {pageItems(page, pages).map((item, index) =>
            item === "gap" ? (
              <span key={`gap-${index}`} className="px-1 text-muted" aria-hidden="true">…</span>
            ) : (
              <button
                key={item}
                type="button"
                onClick={() => onPageChange(item)}
                aria-label={t("pagination.page", { page: item })}
                aria-current={item === page ? "page" : undefined}
                className={clsx(
                  "tabular h-8 min-w-8 rounded-control px-2 font-medium transition-colors",
                  item === page ? "bg-brand-600 text-white" : "text-ink hover:bg-brand-50",
                )}
              >
                {item}
              </button>
            ),
          )}
          <button type="button" className={arrow} onClick={() => onPageChange(page + 1)} disabled={page >= pages}
                  aria-label={t("pagination.next")}>
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </nav>
      )}
    </div>
  );
}
