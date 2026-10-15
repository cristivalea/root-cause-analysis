import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { clsx } from "clsx";
import { ArrowLeft, CheckCircle2, GitCompareArrows, MessageSquareText, ShieldAlert, XCircle } from "lucide-react";
import { ApiError } from "@/api/client";
import { useComparison, useRca, useSummaries } from "@/api/queries";
import { revisionId, type Comparison, type RCARecord } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Card, CardHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { SuccessDialog } from "@/components/ui/Dialog";
import { ConfidencePill, Pill, RcaStatusPill } from "@/components/ui/Pills";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { IncidentDetailsDialog } from "@/components/domain/IncidentDetailsDialog";
import { ProblemSummaryCard } from "@/components/domain/ProblemSummaryCard";
import { CauseDiagram, ResultTabs } from "@/components/rca/ResultTabs";
import { Stepper } from "@/components/rca/Stepper";
import { formatDateTime } from "@/lib/format";
import { uniqueLines } from "@/lib/text";
import { MAX_DECISIONS } from "./ReviewQueuePage";
import { ReviewDecisions, type Decided } from "./ReviewDecisions";

/** What changed since the revision the expert saw before (rca/compare.py, read-only route). */
function ComparisonCard({ found }: { found: Comparison }) {
  const { t } = useI18n();
  const tone = { kept: "neutral", new: "success", dropped: "danger" } as const;
  return (
    <Card className="p-5 sm:p-6">
      <CardHeader title={<span className="flex items-center gap-2"><GitCompareArrows className="h-5 w-5 text-brand-600" aria-hidden="true" />{t("review.compare_title", { revision: found.previous_revision })}</span>} />
      {found.request && (
        <div className="mt-3 rounded-control bg-info-soft/60 px-3 py-2 text-sm text-ink">
          <p className="font-semibold">{t("review.compare_request")}</p>
          <ul className="mt-1 list-disc pl-5">{uniqueLines(found.request).map((line) => <li key={line}>{line}</li>)}</ul>
        </div>
      )}
      <p className={clsx("mt-3 text-sm font-medium", found.main_changed ? "text-warning" : "text-success")}>{found.main_changed ? t("review.compare_main_changed") : t("review.compare_main_same")}</p>
      <ul className="mt-3 flex flex-col gap-2">
        {found.hypotheses.map((change, index) => {
          const cause = change.current ?? change.previous!;
          return (
            // the labels on one line, the cause under them at full width: on a phone the text is not squeezed
            <li key={index} className="text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={tone[change.kind]}>{t(`review.compare_${change.kind}`)}</Pill>
                {change.kind === "kept" && change.previous && change.current && change.previous.confidence !== change.current.confidence && (
                  <span className="text-xs text-muted">{t("review.compare_confidence", { before: t(`confidence.${change.previous.confidence}`), after: t(`confidence.${change.current.confidence}`) })}</span>
                )}
                {change.kind === "new" && change.current && <ConfidencePill confidence={change.current.confidence} />}
              </div>
              <p className={clsx("mt-1 text-ink", change.kind === "dropped" && "line-through decoration-muted")}>{cause.candidate_root_cause}</p>
            </li>
          );
        })}
      </ul>
      <div className="mt-3 flex flex-col gap-1">
        {found.new_evidence.length > 0 && <Disclosure label={t("review.compare_new_evidence", { count: found.new_evidence.length })}><p className="flex flex-wrap gap-1">{found.new_evidence.map((id) => <span key={id} className="tabular rounded bg-success-soft px-1.5 py-0.5 text-xs text-success">{id}</span>)}</p></Disclosure>}
        {found.dropped_evidence.length > 0 && <Disclosure label={t("review.compare_dropped_evidence", { count: found.dropped_evidence.length })}><p className="flex flex-wrap gap-1">{found.dropped_evidence.map((id) => <span key={id} className="tabular rounded bg-neutral-soft px-1.5 py-0.5 text-xs text-muted">{id}</span>)}</p></Disclosure>}
        {found.newly_not_checked.length > 0 && <Disclosure label={t("review.compare_not_checked")}><ul className="list-disc pl-5 text-sm text-ink">{found.newly_not_checked.map((item) => <li key={item}>{item}</li>)}</ul></Disclosure>}
      </div>
    </Card>
  );
}

/** Once decided: what the decision was and what it means. */
function Outcome({ record }: { record: RCARecord }) {
  const { t, language } = useI18n();
  const review = record.review;
  const icons = {
    VALIDATED: <CheckCircle2 className="h-6 w-6 text-success" aria-hidden="true" />, REJECTED: <XCircle className="h-6 w-6 text-danger" aria-hidden="true" />,
    REQUEST_MORE_DETAILS: <MessageSquareText className="h-6 w-6 text-info" aria-hidden="true" />, ESCALATED_MANUAL: <ShieldAlert className="h-6 w-6 text-danger" aria-hidden="true" />,
  } as const;
  const status = record.status as keyof typeof icons;
  if (!(status in icons)) return <Card className="p-5 text-sm text-muted">{t("review.not_waiting")}</Card>;
  return (
    <Card className="flex gap-4 p-5 sm:p-6">
      {icons[status]}
      <div className="min-w-0">
        <p className="font-semibold text-ink">{t(`review.outcome.${status}`)}</p>
        {status === "VALIDATED" && record.final_root_cause && <p className="mt-1 text-[15px] text-ink">{record.final_root_cause}</p>}
        {status === "REQUEST_MORE_DETAILS" && <p className="mt-1 text-sm text-muted">{t("review.outcome_text.REQUEST_MORE_DETAILS")}</p>}
        {review?.comment && <p className="mt-2 text-sm text-ink">“{review.comment}”</p>}
        {review && <p className="mt-1 text-xs text-muted">{t("next.decided_by", { name: review.reviewer, date: formatDateTime(review.decided_at, language) })}</p>}
      </div>
    </Card>
  );
}

export function ReviewPage() {
  const { t } = useI18n();
  const { rcaId = "" } = useParams();
  const record = useRca(rcaId);
  const summaries = useSummaries();
  const comparison = useComparison(record.data ? revisionId(record.data) : rcaId, Boolean(record.data && record.data.revision > 1));
  const [details, setDetails] = useState<string | null>(null);
  const [decided, setDecided] = useState<Decided | null>(null);
  const navigate = useNavigate();

  const back = (
    <Link to="/review" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-ink">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />{t("review.back")}
    </Link>
  );
  if (record.isPending) return <>{back}<Skeleton className="h-32 rounded-card" /><Skeleton className="mt-6 h-96 rounded-card" /></>;
  if (record.isError) {
    return <>{back}{record.error instanceof ApiError && record.error.status === 404 ? <EmptyState title={t("review.not_found")} /> : <ErrorState error={record.error} onRetry={() => void record.refetch()} />}</>;
  }

  const rca = record.data;
  const title = summaries.data?.find((item) => item.rca_id === rca.rca_id)?.title ?? rca.context?.title ?? rca.rca_id;
  const incidentIds = rca.context?.incident_ids ?? [rca.incident_id];
  const waiting = rca.status === "AWAITING_TECHNICAL_REVIEW";

  return (
    <div className="flex flex-col gap-6">
      <div>{back}
        <ProblemSummaryCard
          problemId={rca.problem_id ?? ""}
          title={title}
          incidentIds={incidentIds}
          onDetails={setDetails}
          linkToProblem={false}
          badges={<><RcaStatusPill status={rca.status} /><Pill tone="neutral">{t("inv.revision_of", { revision: rca.revision, rca: rca.rca_id })}</Pill>
            {waiting && <Pill tone="warning">{t("queue.decision_n", { number: rca.review_rounds + 1, max: MAX_DECISIONS })}</Pill>}</>}
        />
      </div>

      {comparison.data && <ComparisonCard found={comparison.data} />}

      {rca.run_status === "COMPLETED" && (
        <Card className="p-5 sm:p-6">
          <h2 className="mb-4 text-lg font-semibold text-ink">{t("review.diagram_title")}</h2>
          <CauseDiagram record={rca} problem={title} />
        </Card>
      )}

      <ResultTabs record={rca} problem={title}
                  tabs={["steps", "causes", "timeline", "summary", "evidence", "not_verified", "evidence_map"]}
                  defaultTab="causes"
                  steps={<Card className="p-5"><Stepper trace={rca.trace} plan={rca.plan} running={rca.run_status === "RUNNING"} failed={rca.run_status === "FAILED"} current={rca.current_step} /></Card>} />

      {waiting ? <ReviewDecisions record={rca} onDecided={setDecided} /> : <Outcome record={rca} />}
      <SuccessDialog open={decided !== null} onOpenChange={(open) => !open && setDecided(null)}
                     title={decided ? t(`success.${decided}_title`) : ""} text={decided ? t(`success.${decided}_text`, { rca: rca.rca_id }) : ""}
                     primary={{ label: t("success.view_details"), onClick: () => setDecided(null) }}
                     secondary={{ label: t("success.home"), onClick: () => navigate("/") }} />
      <IncidentDetailsDialog incidentId={details} onClose={() => setDetails(null)} linkable={false} />
    </div>
  );
}
