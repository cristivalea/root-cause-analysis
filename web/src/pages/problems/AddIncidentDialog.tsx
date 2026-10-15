import { useEffect, useMemo, useState } from "react";
import { clsx } from "clsx";
import { Info, Sparkles } from "lucide-react";
import { useAttachIncident, useCandidates, useUnassigned } from "@/api/queries";
import type { Candidate } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Button, IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Id } from "@/components/ui/Card";
import { TextInput } from "@/components/ui/Field";
import { SearchInput } from "@/components/ui/Search";
import { SeverityPill, SimilarityBar } from "@/components/ui/Pills";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui/States";
import { useReport } from "@/lib/useReport";

/** The one way to add an incident: the incidents the server says may be added (in no problem), the most alike
 * first, searchable. The chosen one is added through the API; the list then comes again from the server, so
 * an added incident disappears from it. */
export function AddIncidentDialog({ problemId, open, onOpenChange, onDetails }: {
  problemId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDetails: (incidentId: string) => void;
}) {
  const { t } = useI18n();
  const report = useReport();
  const candidates = useCandidates(problemId, open);
  const unscored = candidates.isError; // 503: the similarity index is not built
  const unassigned = useUnassigned(open && unscored);
  const attach = useAttachIncident(problemId);
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (open) {
      setQuery("");
      setChosen(null);
      setReason("");
    }
  }, [open]);

  const list: Candidate[] = useMemo(() => {
    if (!unscored) return candidates.data ?? [];
    return (unassigned.data ?? []).map((item) => ({
      incident_id: item.incident_id, title: item.title, service: item.service, severity: item.severity,
      detected_at: item.detected_at, similarity: null, closest_incident_id: null, alike: false,
    }));
  }, [unscored, candidates.data, unassigned.data]);

  const needle = query.trim().toLowerCase();
  const shown = list.filter((item) => !needle || [item.incident_id, item.title, item.service].some((value) => value.toLowerCase().includes(needle)));
  const loading = candidates.isPending || (unscored && unassigned.isPending);

  const add = () => {
    if (!chosen) return;
    attach.mutate({ incidentId: chosen, reason: reason.trim() }, {
      onSuccess: (result) => {
        report.success(t("problem.added", { incident: chosen }), result.warnings);
        onOpenChange(false);
      },
      onError: (error) => report.failure(error),
    });
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !attach.isPending && onOpenChange(next)} size="xl"
            title={t("problem.add_title", { problem: problemId })} description={t("problem.add_text")}
            footer={
              <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-end">
                <TextInput label={t("problem.reason_optional")} value={reason} onChange={(event) => setReason(event.target.value)}
                           className="sm:flex-1" disabled={!chosen} />
                <div className="flex gap-2">
                  <Button onClick={() => onOpenChange(false)} disabled={attach.isPending}>{t("common.cancel")}</Button>
                  <Button variant="primary" onClick={add} disabled={!chosen} loading={attach.isPending}>
                    {chosen ? `${t("problem.add_action")} ${chosen}` : t("problem.add_action")}
                  </Button>
                </div>
              </div>
            }>
      <SearchInput value={query} onChange={setQuery} label={t("problem.add_search")} placeholder={t("problem.add_search")} delay={150} />
      {unscored && <p className="mt-3 rounded-control bg-warning-soft px-3 py-2 text-sm text-warning">{t("problem.add_no_scores")}</p>}
      <div className="mt-4">
        {loading && <SkeletonList rows={5} rowClassName="h-14" />}
        {unscored && unassigned.isError && <ErrorState error={unassigned.error} onRetry={() => void unassigned.refetch()} />}
        {!loading && list.length === 0 && !(unscored && unassigned.isError) && <EmptyState title={t("problem.add_none")} />}
        {shown.length > 0 && (
          <ul role="listbox" aria-label={t("problem.add_title", { problem: problemId })} className="flex flex-col gap-1.5">
            {shown.map((item) => {
              const selected = chosen === item.incident_id;
              return (
                <li key={item.incident_id} role="option" aria-selected={selected}
                    tabIndex={0}
                    onClick={() => setChosen(item.incident_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setChosen(item.incident_id);
                      }
                    }}
                    className={clsx(
                      "grid cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-card border px-3 py-2.5 transition-colors",
                      "sm:grid-cols-[116px_190px_minmax(0,1fr)_130px_auto]",
                      selected ? "border-brand-600 bg-brand-50 ring-1 ring-brand-600" : "border-line hover:border-brand-600/40 hover:bg-brand-50/60",
                    )}>
                  <Id>{item.incident_id}</Id>
                  <span className="order-last col-span-2 flex items-center gap-2 sm:order-none sm:col-span-1">
                    {item.similarity !== null
                      ? <SimilarityBar score={item.similarity} label={t("problem.similarity_of", { percent: Math.round(item.similarity * 100) })} />
                      : <span className="text-xs text-muted">—</span>}
                    {item.alike && (
                      <span title={t("problem.alike_help")} className="inline-flex items-center gap-0.5 text-xs font-semibold text-brand-700">
                        <Sparkles className="h-3 w-3" aria-hidden="true" />{t("problem.alike")}
                      </span>
                    )}
                  </span>
                  <span className="col-span-2 min-w-0 sm:col-span-1">
                    <span className="block truncate text-sm font-medium text-ink" title={item.title}>{item.title}</span>
                    <span className="mt-0.5 block sm:hidden"><SeverityPill severity={item.severity} /></span>
                  </span>
                  <span className="hidden truncate text-sm text-muted sm:block">{item.service}</span>
                  <IconButton label={t("problem.details", { id: item.incident_id })}
                              onClick={(event) => { event.stopPropagation(); onDetails(item.incident_id); }}>
                    <Info className="h-4 w-4" aria-hidden="true" />
                  </IconButton>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Dialog>
  );
}
