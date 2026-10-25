import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { clsx } from "clsx";
import { ArrowLeft, ChevronRight, CircleMinus, FileText, Info, ListChecks, Lock, Microscope, Plus, RotateCcw, Save, ShieldAlert, XCircle } from "lucide-react";
import { useCloseProblem, useDetachIncident, useIncidentIndex, useProblem, useReopenProblem, useSetGuidance, useStartRca } from "@/api/queries";
import { ApiError } from "@/api/client";
import { RCA_STATUSES, type Problem, type ProblemEvent, type RCARecord } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Button, IconButton } from "@/components/ui/Button";
import { Card, CardHeader, Id } from "@/components/ui/Card";
import { ConfirmDialog, SuccessDialog } from "@/components/ui/Dialog";
import { Disclosure } from "@/components/ui/Disclosure";
import { PriorityPill, ProblemStatusPill, RcaStatusPill } from "@/components/ui/Pills";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { IncidentDetailsDialog } from "@/components/domain/IncidentDetailsDialog";
import { formatDate, formatDateTime } from "@/lib/format";
import { useReport } from "@/lib/useReport";
import { AddIncidentDialog } from "./AddIncidentDialog";
import { GuidanceForm } from "./GuidanceForm";
import { draftErrors, draftOf, guidanceOf, sameGuidance, type GuidanceDraft } from "./guidance";

const INCIDENTS_SHOWN = 5;
const EVENTS_SHOWN = 6;
const MAX_REJECTED = 2; // rca/problems.MAX_REJECTED_CASES, shown to explain what the server will do
const ACTIVE: RCARecord["status"][] = ["DRAFT", "AWAITING_TECHNICAL_REVIEW", "REQUEST_MORE_DETAILS", "FAILED"]; // rca/store.ACTIVE_RCA

/** The latest revision of each RCA of the problem, newest RCA first. */
function latestRevisions(rcas: RCARecord[]): RCARecord[] {
  const latest = new Map<string, RCARecord>();
  for (const record of rcas) {
    const current = latest.get(record.rca_id);
    if (!current || record.revision > current.revision) latest.set(record.rca_id, record);
  }
  return [...latest.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function SummaryCard({ problem }: { problem: Problem }) {
  const { t, language } = useI18n();
  return (
    <section className="relative overflow-hidden rounded-[20px] bg-brand-950 p-6 text-white shadow-card sm:p-8">
      <div aria-hidden="true" className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-sky-400/10 blur-3xl" />
      <div className="relative flex flex-wrap items-center gap-2">
        <span className="tabular rounded-full bg-white/10 px-2.5 py-0.5 text-xs font-semibold text-white/80">{problem.problem_id}</span>
        <ProblemStatusPill status={problem.status} />
        <PriorityPill priority={problem.priority} />
        {problem.services.map((service) => (
          <span key={service} className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs font-medium text-white/80">{service}</span>
        ))}
      </div>
      <h1 className="relative mt-3 text-2xl font-semibold leading-tight tracking-tight sm:text-[28px]">{problem.title}</h1>
      <p className="relative mt-2 text-sm text-white/75">
        {t("problem.created_by", { name: problem.created_by, date: formatDate(problem.created_at, language) })}
        {problem.rca_id && <> · {t("problem.closed_by_rca", { rca: problem.rca_id })}</>}
        {!problem.rca_id && problem.close_reason && <> · {t("problem.closed_reason", { date: formatDate(problem.closed_at, language), reason: problem.close_reason })}</>}
      </p>
      {problem.description && problem.description !== problem.title && (
        <div className="relative mt-5 [&_button]:text-sky-200 [&_button:hover]:text-white">
          <Disclosure label={t("problem.description")} icon={<FileText className="h-4 w-4" aria-hidden="true" />}>
            <p className="max-w-3xl text-sm leading-relaxed text-white/80">{problem.description}</p>
          </Disclosure>
        </div>
      )}
    </section>
  );
}

function IncidentsCard({ problem, onDetails }: { problem: Problem; onDetails: (id: string) => void }) {
  const { t } = useI18n();
  const report = useReport();
  const index = useIncidentIndex();
  const detach = useDetachIncident(problem.problem_id);
  const [all, setAll] = useState(false);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const editable = problem.status === "Open"; // rca/problems.INCIDENTS_EDITABLE
  const last = problem.incidents.length === 1;
  const links = [...problem.incidents].sort((a, b) => b.linked_at.localeCompare(a.linked_at));
  const shown = all ? links : links.slice(0, INCIDENTS_SHOWN);

  return (
    <Card className="p-5 sm:p-6">
      <CardHeader
        title={<span className="flex items-center gap-2">{t("problem.incidents")}<span className="tabular rounded-full bg-neutral-soft px-2 text-sm text-muted">{problem.incidents.length}</span></span>}
        action={editable && (
          <Button variant="primary" size="sm" icon={<Plus className="h-4 w-4" aria-hidden="true" />} onClick={() => setAdding(true)}>
            {t("problem.add_incident")}
          </Button>
        )}
      />
      {!editable && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-muted"><Lock className="h-3.5 w-3.5" aria-hidden="true" />{t("problem.incidents_locked")}</p>
      )}
      <ul className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {shown.map((link) => {
          const incident = index?.get(link.incident_id);
          return (
            <li key={link.incident_id} className="group flex min-w-0 items-center gap-2 rounded-card border border-line bg-surface px-3 py-2.5 transition-colors hover:border-brand-600/30 hover:bg-brand-50/60">
              <span className="min-w-0 flex-1">
                <Id className="block">{link.incident_id}</Id>
                {incident ? <span className="block truncate text-sm font-medium text-ink" title={incident.title}>{incident.title}</span>
                  : <Skeleton className="mt-1 h-4 w-3/4" />}
              </span>
              <IconButton label={t("problem.details", { id: link.incident_id })} onClick={() => onDetails(link.incident_id)}>
                <Info className="h-4 w-4" aria-hidden="true" />
              </IconButton>
              {editable && (
                <IconButton variant="danger-ghost" label={last ? t("problem.remove_last") : t("problem.remove", { id: link.incident_id })}
                            disabled={last} onClick={() => setRemoving(link.incident_id)}>
                  <CircleMinus className="h-4 w-4" aria-hidden="true" />
                </IconButton>
              )}
            </li>
          );
        })}
      </ul>
      {links.length > INCIDENTS_SHOWN && (
        <Button variant="ghost" size="sm" className="mt-3" onClick={() => setAll((value) => !value)}>
          {all ? t("common.view_less") : `${t("common.view_more")} (${links.length - INCIDENTS_SHOWN})`}
        </Button>
      )}

      <AddIncidentDialog problemId={problem.problem_id} open={adding} onOpenChange={setAdding} onDetails={onDetails} />
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={t("problem.remove_title", { incident: removing ?? "", problem: problem.problem_id })}
        description={t("problem.remove_text")}
        confirmLabel={t("problem.remove_confirm")}
        tone="danger"
        reason={{ label: t("problem.reason"), required: true, requiredMessage: t("problem.reason_required") }}
        onConfirm={(reason) =>
          detach.mutateAsync({ incidentId: removing!, reason }).then(
            (result) => report.success(t("problem.removed", { incident: removing! }), result.warnings),
            (error: unknown) => { report.failure(error); throw error; },
          )}
      />
    </Card>
  );
}

function NextStepCard({ problem, rcas }: { problem: Problem; rcas: RCARecord[] }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const report = useReport();
  const setGuidance = useSetGuidance(problem.problem_id);
  const start = useStartRca(problem.problem_id);
  const close = useCloseProblem(problem.problem_id);
  const reopen = useReopenProblem(problem.problem_id);
  const [draft, setDraft] = useState<GuidanceDraft>(() => draftOf(problem.guidance));
  const [closing, setClosing] = useState(false);
  const [reopening, setReopening] = useState(false);
  const [changed, setChanged] = useState<"closed" | "reopened" | null>(null);
  const requestKey = useRef<string | null>(null);

  // the saved guidance changed on the server (saved here, or by a start): show it
  const saved = JSON.stringify(problem.guidance);
  useEffect(() => setDraft(draftOf(problem.guidance)), [saved]); // eslint-disable-line react-hooks/exhaustive-deps

  const latest = latestRevisions(rcas);
  const active = latest.find((record) => ACTIVE.includes(record.status));
  const rejected = latest.filter((record) => record.status === "REJECTED");
  const guidance = guidanceOf(draft);
  const invalid = Object.values(draftErrors(draft)).some(Boolean);
  const dirty = !sameGuidance(guidance, problem.guidance);
  const guidanceEditable = problem.status === "Open" || problem.status === "In investigation"; // rca/problems.EDITABLE
  const canStart = problem.status === "Open" && !active;

  const save = () =>
    setGuidance.mutate(guidance, {
      onSuccess: (result) => report.success(guidance ? t("guidance.saved") : t("guidance.cleared"), result.warnings),
      onError: (error) => report.failure(error),
    });

  const startRca = () => {
    requestKey.current ??= crypto.randomUUID(); // one key per start: a repeated click returns the same RCA
    start.mutate({ guidance, requestKey: requestKey.current }, {
      onSuccess: (revision) => {
        requestKey.current = null;
        report.success(t("problem.starting"));
        navigate(`/investigation/${revision.rca_id}`);
      },
      onError: (error) => {
        requestKey.current = null;
        report.failure(error);
      },
    });
  };

  return (
    <Card className="p-5 sm:p-6 lg:sticky lg:top-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">{t("problem.next_step")}</p>

      {active && (
        <div className="mt-3 rounded-card bg-info-soft p-4">
          <p className="font-semibold text-ink">{t("problem.active_rca", { rca: active.rca_id, status: t(`status.rca.${active.status}`) })}</p>
          <p className="mt-1 text-sm text-muted">{t("problem.active_hint")}</p>
          <Button variant="primary" className="mt-3 w-full" icon={<Microscope className="h-4 w-4" aria-hidden="true" />}
                  onClick={() => navigate(`/investigation/${active.rca_id}`)}>
            {t("problem.open_investigation")}
          </Button>
        </div>
      )}

      {problem.status === "Manual" && (
        <div className="mt-3 flex gap-3 rounded-card bg-danger-soft/70 p-4 text-sm text-ink">
          <ShieldAlert className="h-5 w-5 shrink-0 text-danger" aria-hidden="true" />
          <p>{t("problem.manual_text")}</p>
        </div>
      )}
      {problem.status === "Closed" && (
        <div className="mt-3 rounded-card bg-neutral-soft p-4 text-sm text-ink">
          <p>{t("problem.closed_text")}</p>
          <Button className="mt-3 w-full" icon={<RotateCcw className="h-4 w-4" aria-hidden="true" />} onClick={() => setReopening(true)}>
            {t("problem.reopen")}
          </Button>
        </div>
      )}

      {problem.status === "Open" && !active && (
        <>
          <h2 className="mt-2 text-lg font-semibold text-ink">{t("problem.start_title")}</h2>
          <p className="mt-1 text-sm text-muted">{t("problem.start_text")}</p>
          {rejected.length > 0 && (
            <div className="mt-3 rounded-card bg-warning-soft p-3 text-sm text-ink">
              <p>{t("problem.after_rejection", { rca: rejected[0]!.rca_id })}</p>
              <p className="mt-1 text-xs text-muted">{t("problem.rejected_count", { count: rejected.length, maximum: MAX_REJECTED })}</p>
            </div>
          )}
        </>
      )}

      {guidanceEditable && (
        <div className="mt-4 rounded-card border border-line">
          <Disclosure
            className="px-4 py-3"
            defaultOpen={Boolean(problem.guidance)}
            label={<span className="flex items-center gap-2 text-ink">{t("guidance.title")}<span className="text-xs font-normal text-muted">{t("guidance.optional")}</span>
              {dirty && <span className="rounded-full bg-warning-soft px-2 text-[11px] font-semibold text-warning">{t("guidance.unsaved")}</span>}</span>}
          >
            <div className="pb-1 pt-2">
              <GuidanceForm draft={draft} onChange={setDraft} exclude={problem.services} />
              <Button size="sm" className="mt-4" icon={<Save className="h-4 w-4" aria-hidden="true" />} onClick={save}
                      disabled={!dirty || invalid} loading={setGuidance.isPending}>
                {t("guidance.save")}
              </Button>
            </div>
          </Disclosure>
        </div>
      )}

      {canStart && (
        <Button variant="primary" className="mt-4 h-11 w-full text-[15px]" icon={<Microscope className="h-4 w-4" aria-hidden="true" />}
                onClick={startRca} disabled={invalid} loading={start.isPending}>
          {t("problem.start")}
        </Button>
      )}

      {/* closing ends the work on the problem: a quiet link at the bottom, away from the main action */}
      {(problem.status === "Open" || problem.status === "Manual") && (
        <div className="mt-5 border-t border-line pt-3 text-center">
          <button type="button" onClick={() => setClosing(true)}
                  className="inline-flex items-center gap-1.5 rounded-control px-2 py-1 text-sm text-muted transition-colors hover:text-danger focus-visible:text-danger">
            <XCircle className="h-4 w-4" aria-hidden="true" />{t("problem.close_link")}
          </button>
        </div>
      )}

      <ConfirmDialog
        open={closing}
        onOpenChange={setClosing}
        title={t("problem.close_title", { problem: problem.problem_id })}
        description={t("problem.close_text")}
        confirmLabel={t("problem.close")}
        tone="danger"
        reason={{ label: t("problem.reason"), required: true, requiredMessage: t("problem.reason_required") }}
        onConfirm={(reason) => close.mutateAsync(reason).then(
          (result) => { setChanged("closed"); report.success(t("problem.closed", { problem: problem.problem_id }), result.warnings, undefined, true); },
          (error: unknown) => { report.failure(error); throw error; },
        )}
      />
      <ConfirmDialog
        open={reopening}
        onOpenChange={setReopening}
        title={t("problem.reopen_title", { problem: problem.problem_id })}
        description={t("problem.reopen_text")}
        confirmLabel={t("problem.reopen")}
        reason={{ label: t("problem.reason"), required: true, requiredMessage: t("problem.reason_required") }}
        onConfirm={(reason) => reopen.mutateAsync(reason).then(
          (result) => { setChanged("reopened"); report.success(t("problem.reopened", { problem: problem.problem_id }), result.warnings, undefined, true); },
          (error: unknown) => { report.failure(error); throw error; },
        )}
      />
      <SuccessDialog
        open={changed !== null}
        onOpenChange={(open) => !open && setChanged(null)}
        title={changed ? t(`success.${changed}_title`) : ""}
        text={changed ? t(`success.${changed}_text`, { problem: problem.problem_id }) : ""}
        primary={{ label: t("success.view_details"), onClick: () => setChanged(null) }}
        secondary={{ label: t("success.home"), onClick: () => navigate("/") }}
      />
    </Card>
  );
}

function RcasCard({ rcas }: { rcas: RCARecord[] }) {
  const { t, language } = useI18n();
  const latest = latestRevisions(rcas);
  return (
    <Card className="p-5 sm:p-6">
      <CardHeader title={t("problem.rcas")} />
      {latest.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("problem.rcas_none")}</p>
      ) : (
        <ul className="mt-4 flex flex-col gap-2">
          {latest.map((record) => (
            <li key={record.rca_id}>
              <Link to={`/investigation/${record.rca_id}`}
                    className="group flex flex-wrap items-center gap-x-3 gap-y-1 rounded-card border border-line px-4 py-3 transition-colors hover:border-brand-600/40 hover:bg-brand-50">
                <Id>{record.rca_id}</Id>
                <span className="text-sm text-muted">{t("problem.revision", { revision: record.revision })}</span>
                <RcaStatusPill status={record.status} />
                <span className="ml-auto flex items-center gap-1 text-sm text-muted">
                  {formatDateTime(record.created_at, language)}
                  <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function eventText(event: ProblemEvent, t: ReturnType<typeof useI18n>["t"]): string {
  const to = String(event.details.to ?? "");
  const status = event.action === "rca_status"
    ? (RCA_STATUSES as string[]).includes(to) ? t(`status.rca.${to as RCARecord["status"]}`) : to
    : ["Open", "In investigation", "Manual", "Closed"].includes(to) ? t(`status.problem.${to as Problem["status"]}`) : to;
  let text = t(`event.${event.action}`, { incident: event.incident_id ?? "", rca: event.rca_id ?? "", to: status });
  if (event.details.imported) text += ` ${t("event.imported")}`;
  if (event.details.migrated) text += ` ${t("event.migrated")}`;
  if (event.details.manual) text += ` ${t("event.manually")}`;
  return text;
}

function HistoryCard({ events }: { events: ProblemEvent[] }) {
  const { t, language } = useI18n();
  const [all, setAll] = useState(false);
  const ordered = [...events].sort((a, b) => b.at.localeCompare(a.at));
  const shown = all ? ordered : ordered.slice(0, EVENTS_SHOWN);
  return (
    <Card className="p-5 sm:p-6">
      <CardHeader title={<span className="flex items-center gap-2"><ListChecks className="h-5 w-5 text-brand-600" aria-hidden="true" />{t("problem.history")}</span>} />
      {ordered.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("problem.history_none")}</p>
      ) : (
        <ol className="relative mt-4 border-l-2 border-line pl-5">
          {shown.map((event, index) => (
            <li key={`${event.at}-${index}`} className="relative pb-4 last:pb-0">
              <span aria-hidden="true" className={clsx("absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-surface",
                event.action === "rca_status" ? "bg-info" : event.action === "closed" ? "bg-muted" : "bg-brand-600")} />
              <p className="text-sm text-ink"><span className="font-semibold">{event.by}</span> {eventText(event, t)}</p>
              {event.reason && <p className="mt-0.5 text-sm text-muted">“{event.reason}”</p>}
              <p className="mt-0.5 text-xs text-muted">{formatDateTime(event.at, language)}</p>
            </li>
          ))}
        </ol>
      )}
      {ordered.length > EVENTS_SHOWN && (
        <Button variant="ghost" size="sm" className="mt-3" onClick={() => setAll((value) => !value)}>
          {all ? t("common.view_less") : `${t("common.view_more")} (${ordered.length - EVENTS_SHOWN})`}
        </Button>
      )}
    </Card>
  );
}

export function ProblemDetailPage() {
  const { t } = useI18n();
  const { problemId = "" } = useParams();
  const detail = useProblem(problemId);
  const index = useIncidentIndex();
  const [details, setDetails] = useState<string | null>(null);

  const back = (
    <Link to="/problems" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-ink">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />{t("problem.back")}
    </Link>
  );

  if (detail.isPending) {
    return <>{back}<Skeleton className="h-56 rounded-[20px]" /><div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]"><Skeleton className="h-72 rounded-card" /><Skeleton className="h-72 rounded-card" /></div></>;
  }
  if (detail.isError) {
    return <>{back}{detail.error instanceof ApiError && detail.error.status === 404
      ? <EmptyState title={t("problem.not_found")} />
      : <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />}</>;
  }

  const { problem, events, rcas } = detail.data;
  return (
    <>
      {back}
      <SummaryCard problem={problem} />
      {/* small screens read top-down: incidents, next step, RCAs, history; wide screens keep the next step on the right */}
      <div className="mt-6 grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px] lg:grid-rows-[auto_auto_1fr]">
        <div className="min-w-0 lg:col-start-1"><IncidentsCard problem={problem} onDetails={setDetails} /></div>
        <div className="min-w-0 lg:col-start-2 lg:row-span-3 lg:row-start-1 lg:self-stretch">
          <NextStepCard key={problem.problem_id} problem={problem} rcas={rcas} />
        </div>
        <div className="min-w-0 lg:col-start-1"><RcasCard rcas={rcas} /></div>
        <div className="min-w-0 lg:col-start-1"><HistoryCard events={events} /></div>
      </div>
      <IncidentDetailsDialog incidentId={details} known={details ? index?.get(details) : undefined} onClose={() => setDetails(null)} />
    </>
  );
}
