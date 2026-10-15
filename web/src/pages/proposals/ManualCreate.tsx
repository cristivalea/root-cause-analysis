import { useCallback, useMemo, useState } from "react";
import { clsx } from "clsx";
import { Info, Plus, X } from "lucide-react";
import { useCreateProblem } from "@/api/queries";
import type { Incident, Proposal } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Button, IconButton } from "@/components/ui/Button";
import { Card, Id } from "@/components/ui/Card";
import { TextArea, TextInput } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { SeverityPill } from "@/components/ui/Pills";
import { EmptyState } from "@/components/ui/States";
import { formatDate } from "@/lib/format";
import { paginate } from "@/lib/useUrlState";
import { useReport } from "@/lib/useReport";
import { filterIncidents, type IncidentFilters } from "./proposalFilters";
import type { ProposalDone } from "./ProposalCard";

const PAGE_SIZE = 10;

/** A problem from incidents the Problem Manager picks, whatever the proposals say. The incidents offered are
 * the ones in no problem (every one of them is in some proposal); the reason is required by the backend. */
export function ManualCreate({ proposals, incidents, filters, onDetails, onDone }: {
  proposals: Proposal[];
  incidents: Map<string, Incident>;
  filters: IncidentFilters;
  onDetails: (incidentId: string) => void;
  onDone: (done: ProposalDone) => void;
}) {
  const { t, language } = useI18n();
  const report = useReport();
  const create = useCreateProblem();
  const [chosen, setChosen] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);

  const where = useMemo(() => new Map(proposals.flatMap((proposal) => proposal.incident_ids.map((id) => [id, proposal] as const))), [proposals]);
  const free = useMemo(
    () => [...where.keys()].map((id) => incidents.get(id)).filter((item): item is Incident => Boolean(item))
      .sort((a, b) => b.detected_at.localeCompare(a.detected_at)),
    [where, incidents],
  );
  const visible = filterIncidents(free, filters);
  const current = paginate(visible, page, PAGE_SIZE);
  const toggle = useCallback((id: string) => setChosen((list) => list.includes(id) ? list.filter((item) => item !== id) : [...list, id]), []);

  const submit = () => {
    if (!reason.trim()) return setReasonError(t("problem.reason_required"));
    create.mutate({ incidentIds: chosen, title: title.trim(), reason: reason.trim() }, {
      onSuccess: (result) => {
        onDone({ kind: "created", problem: result.problem.problem_id, already: false, warnings: result.warnings });
        setChosen([]);
        setTitle("");
        setReason("");
      },
      onError: (error) => report.failure(error),
    });
  };

  if (free.length === 0) return <EmptyState title={t("manual.none")} />;

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0">
        <p className="mb-3 text-sm text-muted">{t("manual.text")}</p>
        {visible.length === 0 ? <EmptyState title={t("proposals.no_match")} /> : (
          <ul className="flex flex-col gap-1.5" aria-label={t("proposals.kind.manual")}>
            {current.items.map((incident) => {
              const selected = chosen.includes(incident.incident_id);
              return (
                <li key={incident.incident_id}
                    className={clsx("flex items-center gap-3 rounded-card border bg-surface px-3 py-2.5 transition-colors",
                      selected ? "border-brand-600 bg-brand-50 ring-1 ring-brand-600" : "border-line hover:border-brand-600/40 hover:bg-brand-50/50")}>
                  <input type="checkbox" checked={selected} onChange={() => toggle(incident.incident_id)}
                         aria-label={t("manual.select", { id: incident.incident_id })}
                         className="h-4 w-4 shrink-0 cursor-pointer accent-[rgb(var(--brand-600))]" />
                  <button type="button" onClick={() => toggle(incident.incident_id)} className="grid min-w-0 flex-1 cursor-pointer items-center gap-x-4 gap-y-1 text-left sm:grid-cols-[112px_minmax(0,1fr)_80px]">
                    <Id>{incident.incident_id}</Id>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-ink" title={incident.title}>{incident.title}</span>
                      <span className="block truncate text-xs text-muted">{incident.service} · {formatDate(incident.detected_at, language)}</span>
                    </span>
                    <span className="hidden sm:block"><SeverityPill severity={incident.severity} /></span>
                  </button>
                  <IconButton label={t("problem.details", { id: incident.incident_id })} onClick={() => onDetails(incident.incident_id)}>
                    <Info className="h-4 w-4" aria-hidden="true" />
                  </IconButton>
                </li>
              );
            })}
          </ul>
        )}
        <Pagination page={current.page} pageSize={PAGE_SIZE} total={visible.length} onPageChange={setPage} />
      </div>

      <Card className="p-5 lg:sticky lg:top-6">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-semibold text-ink">{t("manual.selected", { count: chosen.length })}</h3>
          {chosen.length > 0 && <Button size="sm" variant="ghost" onClick={() => setChosen([])}>{t("manual.clear")}</Button>}
        </div>
        {chosen.length === 0 ? <p className="mt-2 text-sm text-muted">{t("manual.pick_first")}</p> : (
          <>
            <ul className="mt-3 flex max-h-56 flex-col gap-1.5 overflow-y-auto">
              {chosen.map((id) => {
                const proposal = where.get(id);
                return (
                  <li key={id} className="flex items-start gap-2 rounded-control bg-neutral-soft px-2.5 py-1.5">
                    <span className="min-w-0 flex-1">
                      <Id className="block">{id}</Id>
                      {proposal && (
                        <span className="block text-xs text-muted">
                          {t("manual.now_in")}: {t(`proposals.kind.${proposal.kind}`)}{proposal.problem_id ? ` → ${proposal.problem_id}` : ""}
                        </span>
                      )}
                    </span>
                    <IconButton label={t("manual.clear")} onClick={() => toggle(id)}><X className="h-3.5 w-3.5" aria-hidden="true" /></IconButton>
                  </li>
                );
              })}
            </ul>
            <div className="mt-4 flex flex-col gap-3">
              <TextInput label={t("proposals.title_input")} hint={t("proposals.title_hint")} value={title} onChange={(event) => setTitle(event.target.value)} />
              <TextArea label={t("manual.reason")} hint={t("manual.reason_help")} required rows={3} value={reason} error={reasonError}
                        onChange={(event) => { setReason(event.target.value); setReasonError(null); }} />
              <Button variant="primary" icon={<Plus className="h-4 w-4" aria-hidden="true" />} onClick={submit} loading={create.isPending}>
                {t("manual.create")}
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
