import { useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { ClipboardCheck } from "lucide-react";
import { useRcas, useSummaries } from "@/api/queries";
import type { RCARecord } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Card, Id, PageHeader } from "@/components/ui/Card";
import { FilterPopover, SearchInput } from "@/components/ui/Search";
import { Pagination } from "@/components/ui/Pagination";
import { Pill } from "@/components/ui/Pills";
import { Select, TextInput } from "@/components/ui/Field";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui/States";
import { dayOf, formatDateTime } from "@/lib/format";
import { paginate, useUrlState } from "@/lib/useUrlState";

const DEFAULTS = { q: "", service: "", from: "", to: "", page: "1", size: "5" };
export const MAX_DECISIONS = 3; // rca/store.MAX_REVISIONS

const servicesOf = (record: RCARecord) => record.context?.services ?? [];

/** The RCAs waiting for the expert: the latest revision of each RCA in AWAITING_TECHNICAL_REVIEW, as the
 * API returns them for this role (only RCAs sent to the expert). */
export function ReviewQueuePage() {
  const { t, language } = useI18n();
  const { value, set } = useUrlState(DEFAULTS);
  const waiting = useRcas("AWAITING_TECHNICAL_REVIEW");
  const summaries = useSummaries();
  const titles = useMemo(() => new Map((summaries.data ?? []).map((item) => [item.rca_id, item.title])), [summaries.data]);
  const all = useMemo(() => [...(waiting.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)), [waiting.data]);
  const services = useMemo(() => [...new Set(all.flatMap(servicesOf))].sort(), [all]);

  const needle = value("q").trim().toLowerCase();
  const visible = all.filter((record) =>
    (!needle || [record.rca_id, record.problem_id ?? "", titles.get(record.rca_id) ?? ""].some((item) => item.toLowerCase().includes(needle))) &&
    (!value("service") || servicesOf(record).includes(value("service"))) &&
    (!value("from") || dayOf(record.created_at) >= value("from")) &&
    (!value("to") || dayOf(record.created_at) <= value("to")));
  const size = value("size") === "10" ? 10 : 5;
  const current = paginate(visible, Number(value("page")) || 1, size);
  const active = ["service", "from", "to"].filter((key) => value(key as "service")).length;
  const setQuery = useCallback((q: string) => set({ q }), [set]);

  return (
    <>
      <PageHeader title={t("queue.title")} subtitle={t("queue.subtitle")} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchInput value={value("q")} onChange={setQuery} label={t("queue.search")} placeholder={t("queue.search")} className="sm:max-w-md sm:flex-1" />
        <FilterPopover active={active} onClear={() => set({ service: "", from: "", to: "" })}>
          <Select label={t("queue.filter.service")} value={value("service")} onChange={(event) => set({ service: event.target.value })}>
            <option value="">{t("common.all")}</option>
            {services.map((service) => <option key={service} value={service}>{service}</option>)}
          </Select>
          <div className="grid grid-cols-2 gap-3">
            <TextInput label={t("queue.filter.from")} type="date" value={value("from")} onChange={(event) => set({ from: event.target.value })} />
            <TextInput label={t("queue.filter.to")} type="date" value={value("to")} onChange={(event) => set({ to: event.target.value })} />
          </div>
        </FilterPopover>
      </div>
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
                      <Card className="flex flex-col gap-4 p-4 transition-shadow hover:shadow-pop animate-fade-up sm:flex-row sm:items-center sm:p-5" style={{ animationDelay: `${index * 50}ms` }}>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <Id>{record.problem_id}</Id><span className="text-muted" aria-hidden="true">·</span><Id>{record.rca_id}</Id>
                            {record.revision > 1 ? <Pill tone="info">{t("queue.revision_note", { revision: record.revision })}</Pill> : <Pill tone="warning">{t("queue.new")}</Pill>}
                          </div>
                          <h3 className="mt-1.5 font-semibold leading-snug text-ink">{titles.get(record.rca_id) ?? record.rca_id}</h3>
                          <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                            <span>{t("queue.investigated", { date: formatDateTime(record.created_at, language) })}</span>
                            {servicesOf(record).map((service) => <span key={service} className="rounded-full bg-neutral-soft px-2 py-0.5 font-medium">{service}</span>)}
                            <span>{t("queue.decision_n", { number: record.review_rounds + 1, max: MAX_DECISIONS })}</span>
                          </p>
                        </div>
                        <Link to={`/review/${record.rca_id}`}
                              className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-control bg-brand-600 px-4 text-sm font-medium text-white shadow-card hover:bg-brand-700">
                          <ClipboardCheck className="h-4 w-4" aria-hidden="true" />{t("queue.review")}
                        </Link>
                      </Card>
                    </li>
                  ))}
                </ul>
                <Pagination page={current.page} pageSize={size} total={visible.length} pageSizes={[5, 10]}
                            onPageChange={(page) => set({ page: String(page) })} onPageSizeChange={(next) => set({ size: String(next) })} />
              </>
            ))}
      </div>
    </>
  );
}
