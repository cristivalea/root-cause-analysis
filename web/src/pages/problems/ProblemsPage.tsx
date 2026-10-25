import { useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { clsx } from "clsx";
import { ArrowDown, ArrowUp, ArrowUpDown, Layers } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import type { MessageKey } from "@/i18n/en";
import { useProblems } from "@/api/queries";
import { PROBLEM_STATUSES, type Priority, type Problem } from "@/api/types";
import { Id, PageHeader } from "@/components/ui/Card";
import { PillTabs } from "@/components/ui/PillTabs";
import { ROW_HOVER, RowChevron } from "@/components/ui/RowLink";
import { FilterPopover, SearchInput } from "@/components/ui/Search";
import { Pagination } from "@/components/ui/Pagination";
import { PriorityPill, ProblemStatusPill } from "@/components/ui/Pills";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui/States";
import { Select, TextInput } from "@/components/ui/Field";
import { formatDate } from "@/lib/format";
import { paginate, useUrlState } from "@/lib/useUrlState";
import { countByStatus, filterProblems, sortProblems, type SortDirection, type SortKey, type StatusTab } from "./problemFilters";

const PAGE_SIZE = 10;
const DEFAULTS = { tab: "Open", q: "", priority: "", service: "", min: "1", from: "", to: "", sort: "created", dir: "desc", page: "1" };
const TABS: StatusTab[] = [...PROBLEM_STATUSES, "all"];
const PRIORITIES: Priority[] = ["P1", "P2", "P3", "P4"];
const GRID = "md:grid md:grid-cols-[124px_minmax(0,1fr)_64px_72px_minmax(0,150px)_124px_96px_16px] md:items-center md:gap-4";

const COLUMNS: { key: SortKey | null; label: MessageKey }[] = [
  { key: "problem", label: "problems.col.problem" },
  { key: "title", label: "problems.col.title" },
  { key: "priority", label: "problems.col.priority" },
  { key: "incidents", label: "problems.col.incidents" },
  { key: null, label: "problems.col.services" },
  { key: null, label: "problems.col.status" },
  { key: "created", label: "problems.col.created" },
];

function Services({ services }: { services: string[] }) {
  const shown = services.slice(0, 2);
  return (
    <span className="flex min-w-0 flex-wrap gap-1">
      {shown.map((service) => (
        <span key={service} className="max-w-full truncate rounded-full bg-neutral-soft px-2 py-0.5 text-xs font-medium text-muted">{service}</span>
      ))}
      {services.length > 2 && <span className="rounded-full bg-neutral-soft px-2 py-0.5 text-xs font-medium text-muted">+{services.length - 2}</span>}
    </span>
  );
}

/** One problem as a card-like row. The whole row is a link: click, Enter, or open in a new tab. */
function ProblemRow({ problem }: { problem: Problem }) {
  const { t, language } = useI18n();
  return (
    <li>
      <Link
        to={`/problems/${problem.problem_id}`}
        aria-label={t("problems.row_label", {
          id: problem.problem_id, title: problem.title, status: t(`status.problem.${problem.status}`),
          priority: t(`priority.${problem.priority}`), count: problem.incidents.length,
        })}
        className={clsx(
          "block cursor-pointer rounded-card border border-line bg-surface px-4 py-3.5 shadow-card", ROW_HOVER,
          GRID,
        )}
      >
        <Id className="block">{problem.problem_id}</Id>
        <span className="mt-1 line-clamp-2 font-medium leading-snug text-ink md:mt-0" title={problem.title}>{problem.title}</span>
        <span className="mt-2 flex flex-wrap items-center gap-2 md:contents">
          <span><PriorityPill priority={problem.priority} /></span>
          <span className="tabular inline-flex items-center gap-1.5 text-sm text-ink">
            <Layers className="h-4 w-4 text-muted" aria-hidden="true" />
            {problem.incidents.length}
          </span>
          <Services services={problem.services} />
          <span><ProblemStatusPill status={problem.status} /></span>
          <span className="text-sm text-muted">{formatDate(problem.created_at, language)}</span>
          <RowChevron className="hidden md:block" />
        </span>
      </Link>
    </li>
  );
}

export function ProblemsPage() {
  const { t } = useI18n();
  const { value, set } = useUrlState(DEFAULTS);
  const problems = useProblems();

  const tab = (TABS as string[]).includes(value("tab")) ? (value("tab") as StatusTab) : "Open";
  const filters = {
    tab, query: value("q"), priority: value("priority") as Priority | "", service: value("service"),
    minIncidents: Math.max(1, Number(value("min")) || 1), from: value("from"), to: value("to"),
  };
  const sortKey = value("sort") as SortKey;
  const direction = value("dir") as SortDirection;

  const all = useMemo(() => problems.data ?? [], [problems.data]);
  const counts = useMemo(() => countByStatus(all), [all]);
  const services = useMemo(() => [...new Set(all.flatMap((problem) => problem.services))].sort(), [all]);
  const visible = useMemo(
    () => sortProblems(filterProblems(all, filters), sortKey, direction),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [all, tab, filters.query, filters.priority, filters.service, filters.minIncidents, filters.from, filters.to, sortKey, direction],
  );
  const { items, page } = paginate(visible, Number(value("page")) || 1, PAGE_SIZE);
  const activeFilters = [filters.priority, filters.service, filters.minIncidents > 1 ? "min" : "", filters.from, filters.to].filter(Boolean).length;
  const setQuery = useCallback((q: string) => set({ q }), [set]);

  const sortBy = (key: SortKey) => {
    if (key === sortKey) set({ dir: direction === "asc" ? "desc" : "asc", sort: key });
    else set({ sort: key, dir: key === "created" || key === "incidents" ? "desc" : "asc" });
  };

  return (
    <>
      <PageHeader title={t("problems.title")} subtitle={t("problems.subtitle")} />
      <PillTabs
        label={t("problems.tabs")}
        value={tab}
        onChange={(next) => set({ tab: next })}
        tabs={TABS.map((item) => ({ value: item, label: item === "all" ? t("common.all") : t(`status.problem.${item}`), count: problems.data ? counts[item] : undefined }))}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <SearchInput value={filters.query} onChange={setQuery} label={t("problems.search")} placeholder={t("problems.search")} className="sm:max-w-sm sm:flex-1" />
          <FilterPopover active={activeFilters} onClear={() => set({ priority: "", service: "", min: "1", from: "", to: "" })}>
            <Select label={t("problems.filter.priority")} value={filters.priority} onChange={(event) => set({ priority: event.target.value })}>
              <option value="">{t("common.all")}</option>
              {PRIORITIES.map((item) => <option key={item} value={item}>{t(`priority.${item}`)}</option>)}
            </Select>
            <Select label={t("problems.filter.service")} value={filters.service} onChange={(event) => set({ service: event.target.value })}>
              <option value="">{t("common.all")}</option>
              {services.map((item) => <option key={item} value={item}>{item}</option>)}
            </Select>
            <TextInput label={t("problems.filter.min_incidents")} type="number" min={1} value={filters.minIncidents}
                       onChange={(event) => set({ min: event.target.value })} />
            <div className="grid grid-cols-2 gap-3">
              <TextInput label={t("problems.filter.created_from")} type="date" value={filters.from} max={filters.to || undefined}
                         onChange={(event) => set({ from: event.target.value })} />
              <TextInput label={t("problems.filter.created_to")} type="date" value={filters.to} min={filters.from || undefined}
                         onChange={(event) => set({ to: event.target.value })} />
            </div>
          </FilterPopover>
        </div>

        <div className={clsx("mt-5 hidden px-4 pb-2 text-xs font-semibold uppercase tracking-wide text-muted", GRID)}>
          {COLUMNS.map(({ key, label }) =>
            key ? (
              <button key={label} type="button" onClick={() => sortBy(key)} aria-label={t("problems.sort_by", { column: t(label) })}
                      className="inline-flex items-center gap-1 text-left uppercase hover:text-ink">
                {t(label)}
                {sortKey === key
                  ? direction === "asc" ? <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" /> : <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                  : <ArrowUpDown className="h-3.5 w-3.5 opacity-40" aria-hidden="true" />}
              </button>
            ) : (
              <span key={label}>{t(label)}</span>
            ),
          )}
        </div>

        <div className="mt-3 md:mt-0">
          {problems.isPending && <SkeletonList rows={6} rowClassName="h-[60px]" />}
          {problems.isError && <ErrorState error={problems.error} onRetry={() => void problems.refetch()} />}
          {problems.data && visible.length === 0 && (
            all.some((problem) => tab === "all" || problem.status === tab)
              ? <EmptyState title={t("problems.no_match")} action={<button type="button" onClick={() => set({ q: "", priority: "", service: "", min: "1", from: "", to: "" })} className="font-semibold text-brand-700 hover:underline">{t("common.clear_filters")}</button>} />
              : <EmptyState title={t(tab === "all" ? "problems.empty.all" : `problems.empty.${tab}`)} text={t("problems.empty_hint")} />
          )}
          {items.length > 0 && (
            <ul aria-label={t("problems.title")} className="flex flex-col gap-2">
              {items.map((problem) => <ProblemRow key={problem.problem_id} problem={problem} />)}
            </ul>
          )}
          <Pagination page={page} pageSize={PAGE_SIZE} total={visible.length} onPageChange={(next) => set({ page: String(next) })} />
        </div>
      </PillTabs>
    </>
  );
}
