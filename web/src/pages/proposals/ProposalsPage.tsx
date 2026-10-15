import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Info } from "lucide-react";
import { useIncidents, useProposals } from "@/api/queries";
import type { ProposalKind, Severity } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { PageHeader } from "@/components/ui/Card";
import { PillTabs } from "@/components/ui/PillTabs";
import { FilterPopover, SearchInput } from "@/components/ui/Search";
import { Pagination } from "@/components/ui/Pagination";
import { Select, TextInput } from "@/components/ui/Field";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui/States";
import { SuccessDialog } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { IncidentDetailsDialog } from "@/components/domain/IncidentDetailsDialog";
import { paginate, useUrlState } from "@/lib/useUrlState";
import { ManualCreate } from "./ManualCreate";
import { ProposalCard, type ProposalDone } from "./ProposalCard";
import { countByKind, filterProposals } from "./proposalFilters";

type Tab = ProposalKind | "manual";
const TABS: Tab[] = ["group", "attach", "single", "manual"];
const SEVERITIES: Severity[] = ["SEV-1", "SEV-2", "SEV-3", "SEV-4"];
const SCORES = [0, 85, 90, 95];
const DEFAULTS = { tab: "group", q: "", service: "", severity: "", score: "0", from: "", to: "", page: "1", size: "5" };

export function ProposalsPage() {
  const { t } = useI18n();
  const { value, set } = useUrlState(DEFAULTS);
  const proposals = useProposals();
  const incidents = useIncidents();
  const [details, setDetails] = useState<string | null>(null);
  const [done, setDone] = useState<ProposalDone | null>(null);
  const navigate = useNavigate();
  const notify = useToast();
  const finish = useCallback((result: ProposalDone) => {
    setDone(result);
    for (const warning of result.warnings) notify({ tone: "warning", title: t("problem.warning"), text: warning });
  }, [notify, t]);

  const index = useMemo(() => new Map((incidents.data ?? []).map((item) => [item.incident_id, item])), [incidents.data]);
  const tab = (TABS as string[]).includes(value("tab")) ? (value("tab") as Tab) : "group";
  const size = value("size") === "10" ? 10 : 5;
  const incidentFilters = { query: value("q"), service: value("service"), severity: value("severity") as Severity | "", from: value("from"), to: value("to") };
  const minScore = Number(value("score")) || 0;
  const all = useMemo(() => proposals.data ?? [], [proposals.data]);
  const counts = countByKind(all);
  const services = useMemo(() => [...new Set(all.flatMap((proposal) => proposal.incident_ids.map((id) => index.get(id)?.service ?? "")))].filter(Boolean).sort(), [all, index]);
  const visible = tab === "manual" ? [] : filterProposals(all, index, { ...incidentFilters, kind: tab, minScore });
  const current = paginate(visible, Number(value("page")) || 1, size);
  const active = [incidentFilters.service, incidentFilters.severity, minScore > 0 ? "s" : "", incidentFilters.from, incidentFilters.to].filter(Boolean).length;
  const setQuery = useCallback((q: string) => set({ q }), [set]);
  const loading = proposals.isPending || incidents.isPending;

  return (
    <>
      <PageHeader title={t("proposals.title")} subtitle={t("proposals.subtitle")} />
      <PillTabs
        label={t("proposals.tabs")}
        value={tab}
        onChange={(next) => set({ tab: next })}
        tabs={TABS.map((item) => ({ value: item, label: t(`proposals.kind.${item}`), count: item === "manual" || !proposals.data ? undefined : counts[item] }))}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <SearchInput value={incidentFilters.query} onChange={setQuery} label={t("proposals.search")} placeholder={t("proposals.search")} className="sm:max-w-md sm:flex-1" />
          <FilterPopover active={active} onClear={() => set({ service: "", severity: "", score: "0", from: "", to: "" })}>
            <Select label={t("proposals.filter.service")} value={incidentFilters.service} onChange={(event) => set({ service: event.target.value })}>
              <option value="">{t("common.all")}</option>
              {services.map((item) => <option key={item} value={item}>{item}</option>)}
            </Select>
            <Select label={t("proposals.filter.severity")} value={incidentFilters.severity} onChange={(event) => set({ severity: event.target.value })}>
              <option value="">{t("common.all")}</option>
              {SEVERITIES.map((item) => <option key={item} value={item}>{t(`severity.${item}`)}</option>)}
            </Select>
            {tab !== "manual" && (
              <Select label={t("proposals.filter.min_score")} value={String(minScore)} onChange={(event) => set({ score: event.target.value })}>
                {SCORES.map((score) => <option key={score} value={score}>{score === 0 ? t("proposals.filter.any") : `≥ ${score}%`}</option>)}
              </Select>
            )}
            <div className="grid grid-cols-2 gap-3">
              <TextInput label={t("proposals.filter.from")} type="date" value={incidentFilters.from} onChange={(event) => set({ from: event.target.value })} />
              <TextInput label={t("proposals.filter.to")} type="date" value={incidentFilters.to} onChange={(event) => set({ to: event.target.value })} />
            </div>
          </FilterPopover>
        </div>

        <p className="mt-4 flex items-start gap-2 text-sm text-muted">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" aria-hidden="true" />
          {t(`proposals.hint.${tab}`)} {tab !== "manual" && t("proposals.score_note")}
        </p>

        <div className="mt-4">
          {loading && <SkeletonList rows={size === 5 ? 5 : 6} rowClassName="h-40" />}
          {proposals.isError && <ErrorState error={proposals.error} title={t("proposals.unavailable")} onRetry={() => void proposals.refetch()} />}
          {incidents.isError && <ErrorState error={incidents.error} onRetry={() => void incidents.refetch()} />}
          {!loading && proposals.data && incidents.data && (
            tab === "manual" ? (
              <ManualCreate proposals={all} incidents={index} filters={incidentFilters} onDetails={setDetails} onDone={finish} />
            ) : visible.length === 0 ? (
              counts[tab] === 0 ? <EmptyState title={t(`proposals.none.${tab}`)} /> : <EmptyState title={t("proposals.no_match")} />
            ) : (
              <>
                <div className="grid gap-3 xl:grid-cols-2">
                  {current.items.map((proposal, position) => (
                    <ProposalCard key={proposal.key} proposal={proposal} incidents={index} onDetails={setDetails} index={position} onDone={finish} />
                  ))}
                </div>
                <Pagination page={current.page} pageSize={size} total={visible.length} pageSizes={[5, 10]}
                            onPageChange={(next) => set({ page: String(next) })} onPageSizeChange={(next) => set({ size: String(next) })} />
              </>
            )
          )}
        </div>
      </PillTabs>
      <IncidentDetailsDialog incidentId={details} known={details ? index.get(details) : undefined} onClose={() => setDetails(null)} />
      <SuccessDialog
        open={done !== null}
        onOpenChange={(open) => !open && setDone(null)}
        title={done?.kind === "attached" ? t("success.attached_title") : t("success.created_title")}
        text={!done ? "" : done.already ? t("proposals.already", { problem: done.problem })
          : done.kind === "attached" ? t("success.attached_text", { incident: done.incident ?? "", problem: done.problem })
            : t("success.created_text", { problem: done.problem })}
        primary={{ label: t("success.open_problem"), onClick: () => done && navigate(`/problems/${done.problem}`) }}
        secondary={{ label: t("success.home"), onClick: () => navigate("/") }}
      />
    </>
  );
}
