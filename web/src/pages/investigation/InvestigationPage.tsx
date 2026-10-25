import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { clsx } from "clsx";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, FileSearch, Hourglass, ListChecks, Loader2, MessageSquareText, RotateCcw, Send, ShieldAlert, XCircle } from "lucide-react";
import { ApiError } from "@/api/client";
import { useIncidentIndex, useProblem, useRca, useRevisions, useStartNextRevision, useSubmitReview, useSummaries } from "@/api/queries";
import { revisionId, type RCARecord } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Button } from "@/components/ui/Button";
import { Card, Id, PageHeader } from "@/components/ui/Card";
import { ConfirmDialog, SuccessDialog } from "@/components/ui/Dialog";
import { Disclosure } from "@/components/ui/Disclosure";
import { Pill, RcaStatusPill } from "@/components/ui/Pills";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { IncidentDetailsDialog } from "@/components/domain/IncidentDetailsDialog";
import { ProblemSummaryCard } from "@/components/domain/ProblemSummaryCard";
import { ResultTabs } from "@/components/rca/ResultTabs";
import { Stepper } from "@/components/rca/Stepper";
import { stepTitle, canonical } from "@/components/rca/steps";
import { formatDateTime, formatSeconds } from "@/lib/format";
import { uniqueLines } from "@/lib/text";
import { useReport } from "@/lib/useReport";

/** /investigation without an RCA: where an RCA starts, and the recent ones to continue. */
function NoInvestigation() {
  const { t, language } = useI18n();
  const summaries = useSummaries();
  return (
    <>
      <PageHeader title={t("inv.title")} subtitle={t("inv.subtitle")} />
      <EmptyState icon={<FileSearch className="h-6 w-6" aria-hidden="true" />} title={t("inv.none_title")} text={t("inv.none_text")}
                  action={<Link to="/problems" className="inline-flex h-10 items-center gap-2 rounded-control bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700">{t("inv.go_problems")}<ArrowRight className="h-4 w-4" aria-hidden="true" /></Link>} />
      {summaries.data && summaries.data.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-3 font-semibold text-ink">{t("inv.recent")}</h2>
          <ul className="grid grid-cols-[minmax(0,1fr)] gap-2 md:grid-cols-2">
            {summaries.data.slice(0, 6).map((item) => (
              <li key={item.rca_id}>
                <Link to={`/investigation/${item.rca_id}`} className="group flex items-center gap-3 rounded-card border border-line bg-surface px-4 py-3 shadow-card hover:border-brand-600/40 hover:bg-brand-50">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-ink">{item.title}</span>
                    <span className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-muted"><Id>{item.rca_id}</Id>· {formatDateTime(item.updated_at, language)}</span>
                  </span>
                  <RcaStatusPill status={item.status} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/** What can be done with this revision now, after its whole analysis: one action, or where it stands. */
function NextAction({ record, latest }: { record: RCARecord; latest: boolean }) {
  const { t, language } = useI18n();
  const navigate = useNavigate();
  const report = useReport();
  const submit = useSubmitReview();
  const next = useStartNextRevision();
  const [confirming, setConfirming] = useState(false);
  const [sent, setSent] = useState(false);
  const key = useRef<string | null>(null);
  const review = record.review;
  const sentDialog = (
    <SuccessDialog open={sent} onOpenChange={setSent} title={t("success.sent_title")} text={t("success.sent_text", { rca: record.rca_id })}
                   primary={{ label: t("success.view_history"), onClick: () => navigate(`/history/${record.rca_id}`) }}
                   secondary={{ label: t("success.home"), onClick: () => navigate("/") }} />
  );

  const startNext = () => {
    key.current ??= crypto.randomUUID();
    next.mutate({ rcaId: record.rca_id, requestKey: key.current }, {
      onSuccess: (revision) => { key.current = null; report.success(t("inv.started_again")); navigate(`/investigation/${revisionId(revision)}`); },
      onError: (error) => { key.current = null; report.failure(error); },
    });
  };

  const box = (tone: string, icon: React.ReactNode, title: string, text: React.ReactNode, action?: React.ReactNode) => (
    <Card className={clsx("flex flex-col gap-4 p-5 sm:flex-row sm:items-center", tone)}>
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-surface shadow-card">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-ink">{title}</p>
        <div className="mt-0.5 text-sm text-muted">{text}</div>
      </div>
      {action}
    </Card>
  );
  const decided = review && (
    <>
      {/* the request is saved as the comment and, line by line, as the checks: shown once */}
      {uniqueLines(review.comment, ...review.requested_checks).length > 1
        ? <ul className="mt-1 list-disc pl-5 text-ink">{uniqueLines(review.comment, ...review.requested_checks).map((line) => <li key={line}>{line}</li>)}</ul>
        : review.comment && <p className="mt-1 text-ink">“{review.comment}”</p>}
      <p className="mt-1 text-xs">{t("next.decided_by", { name: review.reviewer, date: formatDateTime(review.decided_at, language) })}</p>
    </>
  );

  if (!latest || record.run_status !== "COMPLETED") return null;
  switch (record.status) {
    case "DRAFT":
      return (
        <>
          {box("border-brand-600/30 bg-brand-50/60", <Send className="h-5 w-5 text-brand-600" aria-hidden="true" />, t("next.ready"), t("next.ready_text"),
            <Button variant="primary" icon={<Send className="h-4 w-4" aria-hidden="true" />} onClick={() => setConfirming(true)}>{t("next.send")}</Button>)}
          <ConfirmDialog open={confirming} onOpenChange={setConfirming} title={t("next.send_title")} description={t("next.send_text")} confirmLabel={t("next.send")}
                         onConfirm={() => submit.mutateAsync(record.rca_id).then(() => setSent(true), (error: unknown) => { report.failure(error); throw error; })} />
          {sentDialog}
        </>
      );
    case "AWAITING_TECHNICAL_REVIEW":
      return <>{box("bg-warning-soft/40", <Hourglass className="h-5 w-5 text-warning" aria-hidden="true" />, t("next.waiting"), t("next.waiting_text"))}{sentDialog}</>;
    case "REQUEST_MORE_DETAILS":
      return box("bg-info-soft/50", <MessageSquareText className="h-5 w-5 text-info" aria-hidden="true" />, t("next.more_title"), <>{t("next.more_text")}{decided}</>,
        <Button variant="primary" icon={<RotateCcw className="h-4 w-4" aria-hidden="true" />} onClick={startNext} loading={next.isPending}>{t("next.start_next")}</Button>);
    case "REJECTED":
      return box("bg-danger-soft/40", <XCircle className="h-5 w-5 text-danger" aria-hidden="true" />, t("next.rejected_title"), <>{t("next.rejected_text")}{decided}</>,
        record.problem_id && <Button onClick={() => navigate(`/problems/${record.problem_id}`)}>{t("inv.open_problem")}</Button>);
    case "VALIDATED":
      return box("bg-success-soft/50", <CheckCircle2 className="h-5 w-5 text-success" aria-hidden="true" />, t("next.validated_title"),
        <><p className="font-medium text-ink">{record.final_root_cause}</p>{decided}</>);
    case "ESCALATED_MANUAL":
      return box("bg-danger-soft/40", <ShieldAlert className="h-5 w-5 text-danger" aria-hidden="true" />, t("inv.manual_title"), <>{t("inv.manual_text")}{decided}</>);
    default:
      return null;
  }
}

function Investigation({ rcaId }: { rcaId: string }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const report = useReport();
  const record = useRca(rcaId);
  const problemId = record.data?.problem_id ?? "";
  const problem = useProblem(problemId);
  const revisions = useRevisions(record.data?.rca_id);
  const index = useIncidentIndex();
  const next = useStartNextRevision();
  const key = useRef<string | null>(null);
  const [details, setDetails] = useState<string | null>(null);

  if (record.isPending) return <div className="flex flex-col gap-6"><Skeleton className="h-36 rounded-card" /><Skeleton className="h-40 rounded-card" /><Skeleton className="h-64 rounded-card" /></div>;
  if (record.isError) {
    return record.error instanceof ApiError && record.error.status === 404
      ? <EmptyState title={t("inv.not_found")} action={<Link to="/investigation" className="font-semibold text-brand-700 hover:underline">{t("inv.title")}</Link>} />
      : <ErrorState error={record.error} onRetry={() => void record.refetch()} />;
  }

  const rca = record.data;
  const running = rca.run_status === "RUNNING";
  const failed = rca.run_status === "FAILED";
  const title = problem.data?.problem.title ?? rca.context?.title ?? rca.problem_id ?? rca.rca_id;
  const incidentIds = problem.data?.problem.incidents.map((link) => link.incident_id) ?? rca.context?.incident_ids ?? [rca.incident_id];
  const all = revisions.data ?? [];
  const latest = all.length === 0 || Math.max(...all.map((item) => item.revision)) === rca.revision;
  const currentTitle = rca.current_step ? stepTitle(canonical(rca.current_step)) : null;

  const runAgain = () => {
    key.current ??= crypto.randomUUID();
    next.mutate({ rcaId: rca.rca_id, requestKey: key.current }, {
      onSuccess: (revision) => { key.current = null; report.success(t("inv.started_again")); navigate(`/investigation/${revisionId(revision)}`); },
      onError: (error) => { key.current = null; report.failure(error); },
    });
  };

  return (
    <div className="flex flex-col gap-6">
      <ProblemSummaryCard
        problemId={rca.problem_id ?? ""}
        title={title}
        incidentIds={incidentIds}
        index={index}
        onDetails={setDetails}
        badges={<><RcaStatusPill status={rca.status} /><Pill tone="neutral">{t("inv.revision_of", { revision: rca.revision, rca: rca.rca_id })}</Pill></>}
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pb-1 pt-1 text-xs text-muted">
          <span className="inline-flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" aria-hidden="true" />{t("inv.took", { duration: formatSeconds(rca.duration_seconds, t), count: rca.evidence.length })}</span>
          {all.length > 1 && (
            <span className="flex flex-wrap items-center gap-1.5">{t("inv.other_revisions")}:
              {all.map((item) => (
                <Link key={item.revision} to={`/investigation/${revisionId(item)}`} aria-current={item.revision === rca.revision ? "page" : undefined}
                      className={clsx("rounded-full px-2 py-0.5 font-semibold", item.revision === rca.revision ? "bg-brand-600 text-white" : "bg-neutral-soft text-ink hover:bg-brand-100")}>
                  R{item.revision}
                </Link>
              ))}
            </span>
          )}
        </div>
      </ProblemSummaryCard>

      {running && (
        <div role="status" className="flex items-start gap-3 rounded-card border border-info/20 bg-info-soft/60 px-5 py-4">
          <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-info" aria-hidden="true" />
          <div>
            <p className="font-semibold text-ink">{t("inv.running_title")}</p>
            <p className="mt-0.5 text-sm text-muted">{t("inv.running_text")}</p>
            {currentTitle && <p className="mt-1 text-sm font-medium text-info">{t("inv.running_now", { step: t(currentTitle) })}</p>}
          </div>
        </div>
      )}
      {failed && (
        <div role="alert" className="flex flex-col gap-3 rounded-card border border-danger/20 bg-danger-soft/60 px-5 py-4 sm:flex-row sm:items-start">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-ink">{t("inv.failed_title")}</p>
            <p className="mt-0.5 text-sm text-muted">{t("inv.failed_text")}</p>
            {rca.error && <details className="mt-2 text-xs text-muted"><summary className="cursor-pointer font-medium">{t("common.technical_detail")}</summary><p className="mt-1 break-words">{rca.error}</p></details>}
          </div>
          {latest && rca.status === "FAILED" && <Button variant="primary" icon={<RotateCcw className="h-4 w-4" aria-hidden="true" />} onClick={runAgain} loading={next.isPending}>{t("inv.try_again")}</Button>}
        </div>
      )}

      {/* the steps matter while the analysis runs or after it stopped; once it is done they fold into one line */}
      {rca.run_status === "COMPLETED" ? (
        <Card className="px-5 py-3 sm:px-6">
          <Disclosure label={t("inv.steps_toggle")} icon={<ListChecks className="h-4 w-4" aria-hidden="true" />}>
            <div className="pt-3">
              <Stepper trace={rca.trace} plan={rca.plan} running={running} failed={failed} current={rca.current_step} record={rca} />
            </div>
          </Disclosure>
        </Card>
      ) : (
        <Card className="p-5 sm:p-6">
          <h2 className="mb-5 text-lg font-semibold text-ink">{t("inv.steps")}</h2>
          <Stepper trace={rca.trace} plan={rca.plan} running={running} failed={failed} current={rca.current_step} record={rca} />
        </Card>
      )}

      {rca.run_status === "COMPLETED" && (
        <>
          <section aria-label={t("inv.results")}>
            <ResultTabs record={rca} problem={title}
                        tabs={["causes", "summary", "evidence", "not_verified", "timeline", "checks", "cause_diagram"]}
                        defaultTab="causes" />
          </section>
          <NextAction record={rca} latest={latest} />
        </>
      )}
      <IncidentDetailsDialog incidentId={details} known={details ? index?.get(details) : undefined} onClose={() => setDetails(null)} />
    </div>
  );
}

export function InvestigationPage() {
  const { rcaId } = useParams();
  return rcaId ? <Investigation key={rcaId} rcaId={rcaId} /> : <NoInvestigation />;
}
