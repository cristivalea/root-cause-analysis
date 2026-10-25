import { useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { clsx } from "clsx";
import { ClipboardCheck, Eye } from "lucide-react";
import { useRcas, useSummaries } from "@/api/queries";
import type { RCARecord, RCASummary } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Card, Id, PageHeader } from "@/components/ui/Card";
import { FilterPopover, SearchInput } from "@/components/ui/Search";
import { Pagination } from "@/components/ui/Pagination";
import { Pill, RcaStatusPill } from "@/components/ui/Pills";
import { PillTabs } from "@/components/ui/PillTabs";
import { ROW_HOVER, RowChevron, STRETCHED_LINK } from "@/components/ui/RowLink";
import { Select, TextInput } from "@/components/ui/Field";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui/States";
import { dayOf, formatDateTime } from "@/lib/format";
import { paginate, useUrlState } from "@/lib/useUrlState";

type Tab = "waiting" | "checked";
const TABS: Tab[] = ["waiting", "checked"];
const DEFAULTS = { tab: "waiting", q: "", service: "", from: "", to: "", page: "1", size: "5" };
export const MAX_DECISIONS = 3; // rca/store.MAX_REVISIONS

const servicesOf = (record: RCARecord) => record.context?.services ?? [];

/** The RCAs the expert has decided on at least once and that wait for nothing now, the most recently changed
 * first. Opened read-only: the review page shows the decision instead of the buttons. */
function Checked({ items, total, onPage, onSize, page, size }: {
  items: RCASummary[]; total: number; page: number; size: number; onPage: (page: number) => void; onSize: (size: number) => void;
}) {
  const { t, language } = useI18n();
  return (
    <>
      <ul className="flex flex-col gap-3">
        {items.map((summary, index) => (
          <li key={summary.rca_id}>
            <Card className={clsx("relative flex items-center gap-4 p-4 animate-fade-up sm:p-5", ROW_HOVER)} style={{ animationDelay: `${index * 50}ms` }}>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <RcaStatusPill status={summary.status} />
                  <span className="text-xs text-muted">{t("case.decisions", { count: summary.review_rounds, max: MAX_DECISIONS })}</span>
                </div>
                <h3 className="mt-1.5 font-semibold leading-snug text-ink">
                  <Link to={`/review/${summary.rca_id}`} className={STRETCHED_LINK}>{summary.title}</Link>
                </h3>
                <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
                  <Id>{summary.problem_id}</Id><span aria-hidden="true">·</span><Id>{summary.rca_id}</Id><span aria-hidden="true">·</span>
                  <span>{t("history.updated", { date: formatDateTime(summary.updated_at, language) })}</span>
                </p>
              </div>
              <RowChevron />
            </Card>
          </li>
        ))}
      </ul>
      <Pagination page={page} pageSize={size} total={total} pageSizes={[5, 10]} onPageChange={onPage} onPageSizeChange={onSize} />
    </>
  );
}

/** Two tabs: the RCAs waiting for the expert (the latest revision of each RCA in AWAITING_TECHNICAL_REVIEW), and
 * the ones already checked. The API returns only the RCAs sent to the expert, for both. */
export function ReviewQueuePage() {
  const { t, language } = useI18n();
  const { value, set } = useUrlState(DEFAULTS);
  const waiting = useRcas("AWAITING_TECHNICAL_REVIEW");
  const summaries = useSummaries();
  const titles = useMemo(() => new Map((summaries.data ?? []).map((item) => [item.rca_id, item.title])), [summaries.data]);
  const all = useMemo(() => [...(waiting.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)), [waiting.data]);
  const services = useMemo(() => [...new Set(all.flatMap(servicesOf))].sort(), [all]);
  const tab: Tab = value("tab") === "checked" ? "checked" : "waiting";
  const checked = useMemo(() => (summaries.data ?? [])
    .filter((summary) => summary.review_rounds > 0 && summary.status !== "AWAITING_TECHNICAL_REVIEW")
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at)), [summaries.data]);

  const needle = value("q").trim().toLowerCase();
  const visible = all.filter((record) =>
    (!needle || [record.rca_id, record.problem_id ?? "", titles.get(record.rca_id) ?? ""].some((item) => item.toLowerCase().includes(needle))) &&
    (!value("service") || servicesOf(record).includes(value("service"))) &&
    (!value("from") || dayOf(record.created_at) >= value("from")) &&
    (!value("to") || dayOf(record.created_at) <= value("to")));
  const size = value("size") === "10" ? 10 : 5;
  const current = paginate(visible, Number(value("page")) || 1, size);
  const checkedVisible = checked.filter((summary) =>
    (!needle || [summary.rca_id, summary.problem_id, summary.title].some((item) => item.toLowerCase().includes(needle))) &&
    (!value("from") || dayOf(summary.updated_at) >= value("from")) &&
    (!value("to") || dayOf(summary.updated_at) <= value("to")));
  const checkedPage = paginate(checkedVisible, Number(value("page")) || 1, size);
  const active = (tab === "waiting" ? ["service", "from", "to"] : ["from", "to"]).filter((key) => value(key as "service")).length;
  const setQuery = useCallback((q: string) => set({ q }), [set]);

  return (
    <>
      <PageHeader title={t("queue.title")} subtitle={t("queue.subtitle")} />
      <PillTabs label={t("queue.tabs")} value={tab} onChange={(next) => set({ tab: next, page: "1" })}
                tabs={TABS.map((item) => ({ value: item, label: t(`queue.tab.${item}`),
                  count: item === "waiting" ? waiting.data?.length : summaries.data ? checked.length : undefined }))}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <SearchInput value={value("q")} onChange={setQuery} label={t("queue.search")} placeholder={t("queue.search")} className="sm:max-w-md sm:flex-1" />
          <FilterPopover active={active} onClear={() => set({ service: "", from: "", to: "" })}>
            {tab === "waiting" && (
              <Select label={t("queue.filter.service")} value={value("service")} onChange={(event) => set({ service: event.target.value })}>
                <option value="">{t("common.all")}</option>
                {services.map((service) => <option key={service} value={service}>{service}</option>)}
              </Select>
            )}
            <div className="grid grid-cols-2 gap-3">
              <TextInput label={t("queue.filter.from")} type="date" value={value("from")} onChange={(event) => set({ from: event.target.value })} />
              <TextInput label={t("queue.filter.to")} type="date" value={value("to")} onChange={(event) => set({ to: event.target.value })} />
            </div>
          </FilterPopover>
        </div>
        {tab === "checked" ? (
          <div className="mt-5">
            {summaries.isPending && <SkeletonList rows={size} rowClassName="h-24" />}
            {summaries.isError && <ErrorState error={summaries.error} onRetry={() => void summaries.refetch()} />}
            {summaries.data && (checked.length === 0 ? <EmptyState icon={<Eye className="h-6 w-6" aria-hidden="true" />} title={t("queue.checked_empty")} />
              : checkedVisible.length === 0 ? <EmptyState title={t("queue.no_match")} />
                : <Checked items={checkedPage.items} total={checkedVisible.length} page={checkedPage.page} size={size}
                           onPage={(page) => set({ page: String(page) })} onSize={(next) => set({ size: String(next) })} />)}
          </div>
        ) : (
          <div className="mt-5">
            {waiting.isPending && <SkeletonList rows={size} rowClassName="h-24" />}
            {waiting.isError && <ErrorState error={waiting.error} onRetry={() => void waiting.refetch()} />}
            {waiting.data && (all.length === 0 ? <EmptyState icon={<ClipboardCheck className="h-6 w-6" aria-hidden="true" />} title={t("queue.empty")} text={t("queue.empty_hint")} />
              : visible.length === 0 ? <EmptyState title={t("queue.no_match")} />
                : (
                  <>
                    <ul className="flex flex-col gap-3">
                      {current.items.map((record, index) => (
                        <li key={record.rca_id}>
                          <Card className={clsx("relative flex items-center gap-4 p-4 animate-fade-up sm:p-5", ROW_HOVER)} style={{ animationDelay: `${index * 50}ms` }}>
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <Id>{record.problem_id}</Id><span className="text-muted" aria-hidden="true">·</span><Id>{record.rca_id}</Id>
                                {record.revision > 1 ? <Pill tone="info">{t("queue.revision_note", { revision: record.revision })}</Pill> : <Pill tone="warning">{t("queue.new")}</Pill>}
                              </div>
                              <h3 className="mt-1.5 font-semibold leading-snug text-ink">
                                <Link to={`/review/${record.rca_id}`} className={STRETCHED_LINK}>{titles.get(record.rca_id) ?? record.rca_id}</Link>
                              </h3>
                              <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                                <span>{t("queue.investigated", { date: formatDateTime(record.created_at, language) })}</span>
                                {servicesOf(record).map((service) => <span key={service} className="rounded-full bg-neutral-soft px-2 py-0.5 font-medium">{service}</span>)}
                                <span>{t("queue.decision_n", { number: record.review_rounds + 1, max: MAX_DECISIONS })}</span>
                              </p>
                            </div>
                            <RowChevron />
                          </Card>
                        </li>
                      ))}
                    </ul>
                    <Pagination page={current.page} pageSize={size} total={visible.length} pageSizes={[5, 10]}
                                onPageChange={(page) => set({ page: String(page) })} onPageSizeChange={(next) => set({ size: String(next) })} />
                  </>
                ))}
          </div>
        )}
      </PillTabs>
    </>
  );
}
