import { useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { FolderOpen, GitBranch, Loader2 } from "lucide-react";
import { useCases, useProblems, useSummaries } from "@/api/queries";
import { RCA_STATUSES, type RCARecord, type RCASummary } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Card, Id, PageHeader } from "@/components/ui/Card";
import { FilterPopover, SearchInput } from "@/components/ui/Search";
import { Pagination } from "@/components/ui/Pagination";
import { RcaStatusPill } from "@/components/ui/Pills";
import { Select, TextInput } from "@/components/ui/Field";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui/States";
import { formatDate, formatDateTime } from "@/lib/format";
import { paginate, useUrlState } from "@/lib/useUrlState";
import { filterHistory, type HistoryFilters } from "./historyFilters";

const DEFAULTS = { q: "", status: "", service: "", from: "", to: "", page: "1", size: "5" };

function Outcome({ rca, latest }: { rca: RCASummary; latest: RCARecord | undefined }) {
  const { t, language } = useI18n();
  if (latest?.run_status === "RUNNING") {
    return <span className="inline-flex items-center gap-1.5 text-info"><Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />{t("history.running", { revision: latest.revision })}</span>;
  }
  if (rca.status === "AWAITING_TECHNICAL_REVIEW") return <span>{t("history.awaiting")}</span>;
  const review = latest?.review;
  if (review) return <span>{t("history.decision", { decision: t(`decision.${review.decision}`), name: review.reviewer, date: formatDate(review.decided_at, language) })}</span>;
  return <span>{t("history.no_decision")}</span>;
}

function RcaCard({ rca, latest, index }: { rca: RCASummary; latest: RCARecord | undefined; index: number }) {
  const { t, language } = useI18n();
  return (
    <Card className="flex flex-col gap-4 p-4 transition-shadow hover:shadow-pop animate-fade-up sm:flex-row sm:items-center sm:p-5" style={{ animationDelay: `${index * 50}ms` }}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Id>{rca.rca_id}</Id>
          <span className="text-muted" aria-hidden="true">·</span>
          <Link to={`/problems/${rca.problem_id}`} className="tabular text-[13px] font-semibold text-brand-700 hover:underline">{rca.problem_id}</Link>
          <RcaStatusPill status={rca.status} />
        </div>
        <h3 className="mt-1.5 font-semibold leading-snug text-ink">{rca.title}</h3>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
          <span className="inline-flex items-center gap-1"><GitBranch className="h-3.5 w-3.5" aria-hidden="true" />{rca.revisions === 1 ? t("history.revisions_one") : t("history.revisions", { count: rca.revisions })}</span>
          <span>{t("history.started", { date: formatDate(rca.created_at, language) })}</span>
          <span>{t("history.updated", { date: formatDateTime(rca.updated_at, language) })}</span>
        </p>
        <p className="mt-1 text-sm text-ink"><Outcome rca={rca} latest={latest} /></p>
      </div>
      <Link to={`/history/${rca.rca_id}`}
            className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-control bg-brand-600 px-4 text-sm font-medium text-white shadow-card hover:bg-brand-700">
        <FolderOpen className="h-4 w-4" aria-hidden="true" />{t("history.open_case")}
      </Link>
    </Card>
  );
}

export function HistoryPage() {
  const { t } = useI18n();
  const { value, set } = useUrlState(DEFAULTS);
  const summaries = useSummaries();
  const cases = useCases();
  const problems = useProblems();

  const revisions = useMemo(() => new Map((cases.data ?? []).filter((list) => list.length > 0).map((list) => [list[0]!.rca_id, list])), [cases.data]);
  const servicesOf = useMemo(() => new Map((problems.data ?? []).map((problem) => [problem.problem_id, problem.services])), [problems.data]);
  const services = useMemo(() => [...new Set([...servicesOf.values()].flat())].sort(), [servicesOf]);
  const filters: HistoryFilters = { query: value("q"), status: value("status") as HistoryFilters["status"], service: value("service"), from: value("from"), to: value("to") };
  const all = summaries.data ?? [];
  const visible = filterHistory(all, revisions, servicesOf, filters);
  const size = value("size") === "10" ? 10 : 5;
  const current = paginate(visible, Number(value("page")) || 1, size);
  const active = [filters.status, filters.service, filters.from, filters.to].filter(Boolean).length;
  const setQuery = useCallback((q: string) => set({ q }), [set]);
  const latestOf = (rcaId: string) => {
    const list = revisions.get(rcaId);
    return list ? list.reduce((a, b) => (b.revision > a.revision ? b : a)) : undefined;
  };

  return (
    <>
      <PageHeader title={t("history.title")} subtitle={t("history.subtitle")} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchInput value={filters.query} onChange={setQuery} label={t("history.search")} placeholder={t("history.search")} className="sm:max-w-lg sm:flex-1" />
        <FilterPopover active={active} onClear={() => set({ status: "", service: "", from: "", to: "" })}>
          <Select label={t("history.filter.status")} value={filters.status} onChange={(event) => set({ status: event.target.value })}>
            <option value="">{t("common.all")}</option>
            {RCA_STATUSES.map((status) => <option key={status} value={status}>{t(`status.rca.${status}`)}</option>)}
          </Select>
          <Select label={t("history.filter.service")} value={filters.service} onChange={(event) => set({ service: event.target.value })}>
            <option value="">{t("common.all")}</option>
            {services.map((service) => <option key={service} value={service}>{service}</option>)}
          </Select>
          <div className="grid grid-cols-2 gap-3">
            <TextInput label={t("history.filter.from")} type="date" value={filters.from} onChange={(event) => set({ from: event.target.value })} />
            <TextInput label={t("history.filter.to")} type="date" value={filters.to} onChange={(event) => set({ to: event.target.value })} />
          </div>
        </FilterPopover>
      </div>
      <div className="mt-5">
        {(summaries.isPending || cases.isPending) && <SkeletonList rows={size} rowClassName="h-28" />}
        {summaries.isError && <ErrorState error={summaries.error} onRetry={() => void summaries.refetch()} />}
        {summaries.data && cases.data && (
          all.length === 0 ? <EmptyState title={t("history.none")} text={t("history.none_hint")} />
            : visible.length === 0 ? <EmptyState title={t("history.no_match")} />
              : (
                <>
                  <div className="flex flex-col gap-3">
                    {current.items.map((rca, index) => <RcaCard key={rca.rca_id} rca={rca} latest={latestOf(rca.rca_id)} index={index} />)}
                  </div>
                  <Pagination page={current.page} pageSize={size} total={visible.length} pageSizes={[5, 10]}
                              onPageChange={(page) => set({ page: String(page) })} onPageSizeChange={(next) => set({ size: String(next) })} />
                </>
              )
        )}
      </div>
    </>
  );
}
