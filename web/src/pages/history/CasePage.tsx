import { Link, useParams } from "react-router-dom";
import { clsx } from "clsx";
import { ArrowLeft, ArrowUpRight, CheckCircle2, Clock3, FileSearch, Microscope } from "lucide-react";
import { ApiError } from "@/api/client";
import { useRcaHistory, useRevisions } from "@/api/queries";
import { revisionId, type RCARecord, type RCAStatusChange } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Card, CardHeader, Id } from "@/components/ui/Card";
import { Pill, RcaStatusPill } from "@/components/ui/Pills";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { formatDateTime, formatSeconds } from "@/lib/format";
import { uniqueLines } from "@/lib/text";

const MAX_DECISIONS = 3; // rca/store.MAX_REVISIONS, shown to explain the limit

function StatusHistory({ changes }: { changes: RCAStatusChange[] }) {
  const { t, language } = useI18n();
  return (
    <Card className="p-5 sm:p-6">
      <CardHeader title={t("case.status_history")} />
      <ol className="relative mt-4 border-l-2 border-line pl-5">
        {changes.map((change, index) => (
          <li key={index} className="relative pb-4 last:pb-0">
            <span aria-hidden="true" className={clsx("absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-surface",
              change.decision ? "bg-warning" : change.to_status === "VALIDATED" ? "bg-success" : "bg-brand-600")} />
            <div className="flex flex-wrap items-center gap-2 text-sm">
              {change.from_status ? <><RcaStatusPill status={change.from_status} /><span className="text-muted">→</span></> : <span className="text-muted">{t("case.created")} →</span>}
              <RcaStatusPill status={change.to_status} />
            </div>
            <p className="mt-1 text-sm text-ink"><span className="font-semibold">{change.by}</span>{change.comment && <> · “{change.comment}”</>} {change.details.migrated ? <span className="text-xs text-muted">{t("case.migrated")}</span> : null}</p>
            <p className="mt-0.5 text-xs text-muted">{formatDateTime(change.at, language)}{change.revision_id && <> · {change.revision_id}</>}</p>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function RevisionCard({ record, latest }: { record: RCARecord; latest: boolean }) {
  const { t, language } = useI18n();
  const review = record.review;
  const tone = record.run_status === "RUNNING" ? "info" : record.run_status === "FAILED" ? "danger" : "success";
  return (
    <li className="relative">
      <Card className={clsx("p-5", latest && "border-brand-600/40 ring-1 ring-brand-600/15")}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-ink">{t("case.revision", { revision: record.revision })}</span>
              <Id>{revisionId(record)}</Id>
              <Pill tone={tone}>{t(`case.run.${record.run_status}`)}</Pill>
              <RcaStatusPill status={record.status} />
            </div>
            <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
              <span>{formatDateTime(record.created_at, language)}</span>
              <span className="inline-flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" aria-hidden="true" />{formatSeconds(record.duration_seconds, t)}</span>
              <span className="inline-flex items-center gap-1"><FileSearch className="h-3.5 w-3.5" aria-hidden="true" />{t("inv.evidence_count", { count: record.evidence.length })}</span>
            </p>
            {record.revision > 1 && <p className="mt-1 text-xs font-medium text-info">{t("case.answers", { revision: record.revision - 1 })}</p>}
          </div>
          <Link to={`/investigation/${revisionId(record)}`}
                className="inline-flex h-9 shrink-0 items-center gap-2 rounded-control border border-line bg-surface px-3 text-sm font-medium text-ink shadow-card hover:border-brand-600/40 hover:bg-brand-50">
            <Microscope className="h-4 w-4" aria-hidden="true" />{t("case.open_investigation")}
          </Link>
        </div>
        {record.context?.expert_request && (
          <div className="mt-3 rounded-control bg-info-soft/60 px-3 py-2 text-sm text-ink"><p className="font-semibold">{t("case.request")}</p><ul className="mt-1 list-disc pl-5">{uniqueLines(record.context.expert_request).map((line) => <li key={line}>{line}</li>)}</ul></div>
        )}
        {record.error && <p className="mt-3 break-words rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">{record.error}</p>}
        <div className="mt-3 border-t border-line pt-3 text-sm">
          {review ? (
            <>
              <p className="text-ink"><span className="font-semibold">{t(`decision.${review.decision}`)}</span> · {review.reviewer} · <span className="text-muted">{formatDateTime(review.decided_at, language)}</span></p>
              {uniqueLines(review.comment, ...review.requested_checks).length > 1
                ? <ul className="mt-1 list-disc pl-5 text-muted">{uniqueLines(review.comment, ...review.requested_checks).map((item) => <li key={item}>{item}</li>)}</ul>
                : review.comment && <p className="mt-1 text-muted">“{review.comment}”</p>}
            </>
          ) : <p className="text-muted">{t("case.no_review")}</p>}
        </div>
      </Card>
    </li>
  );
}

export function CasePage() {
  const { t, language } = useI18n();
  const { rcaId = "" } = useParams();
  const history = useRcaHistory(rcaId);
  const revisions = useRevisions(rcaId);
  const back = (
    <Link to="/history" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-ink">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />{t("case.back")}
    </Link>
  );
  if (history.isPending || revisions.isPending) return <>{back}<Skeleton className="h-32 rounded-card" /><Skeleton className="mt-6 h-64 rounded-card" /></>;
  if (history.isError) {
    return <>{back}{history.error instanceof ApiError && history.error.status === 404 ? <EmptyState title={t("case.not_found")} /> : <ErrorState error={history.error} onRetry={() => void history.refetch()} />}</>;
  }
  const { rca, history: changes } = history.data;
  const runs = [...(revisions.data ?? [])].sort((a, b) => b.revision - a.revision);
  const validated = runs.find((record) => record.status === "VALIDATED" && record.final_root_cause);

  return (
    <>
      {back}
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-4 bg-gradient-to-r from-brand-50 to-surface px-5 py-5 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2"><Id>{rca.rca_id}</Id><RcaStatusPill status={rca.status} /></div>
            <h1 className="mt-1.5 text-xl font-semibold leading-snug tracking-tight text-ink sm:text-2xl">{rca.title}</h1>
            <p className="mt-1.5 flex flex-wrap gap-x-3 text-xs text-muted">
              <span>{rca.revisions === 1 ? t("history.revisions_one") : t("history.revisions", { count: rca.revisions })}</span>
              <span>{t("case.decisions", { count: rca.review_rounds, max: MAX_DECISIONS })}</span>
              <span>{t("history.started", { date: formatDateTime(rca.created_at, language) })}</span>
              <span>{t("history.updated", { date: formatDateTime(rca.updated_at, language) })}</span>
            </p>
          </div>
          <Link to={`/problems/${rca.problem_id}`}
                className="inline-flex h-9 items-center gap-1.5 rounded-control border border-line bg-surface px-3 text-sm font-medium text-ink shadow-card hover:border-brand-600/40 hover:bg-brand-50">
            {t("case.problem", { problem: rca.problem_id })}<ArrowUpRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      </Card>

      {validated && (
        <Card className="mt-6 flex gap-4 border-success/30 bg-success-soft/50 p-5">
          <CheckCircle2 className="mt-0.5 h-6 w-6 shrink-0 text-success" aria-hidden="true" />
          <div>
            <p className="font-semibold text-ink">{t("case.final")}</p>
            <p className="mt-1 text-[15px] leading-relaxed text-ink">{validated.final_root_cause}</p>
            <p className="mt-1 text-xs text-muted">{t("case.final_text")}</p>
          </div>
        </Card>
      )}

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section>
          <h2 className="text-lg font-semibold text-ink">{t("case.revisions")}</h2>
          <p className="mt-1 text-sm text-muted">{t("case.revisions_text")}</p>
          <ol className="mt-4 flex flex-col gap-3">
            {runs.map((record, index) => <RevisionCard key={record.revision} record={record} latest={index === 0} />)}
          </ol>
        </section>
        <StatusHistory changes={changes} />
      </div>
    </>
  );
}
