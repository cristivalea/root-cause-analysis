import { useEffect, useState } from "react";
import { clsx } from "clsx";
import { AlertTriangle, CheckCircle2, MessageSquareText, XCircle } from "lucide-react";
import { useApplyReview, type ReviewRequest } from "@/api/queries";
import type { RCARecord } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog, Dialog } from "@/components/ui/Dialog";
import { Disclosure } from "@/components/ui/Disclosure";
import { TextArea } from "@/components/ui/Field";
import { ConfidencePill } from "@/components/ui/Pills";
import { useReport } from "@/lib/useReport";
import { GuidanceForm } from "@/pages/problems/GuidanceForm";
import { draftErrors, draftOf, guidanceOf, type GuidanceDraft } from "@/pages/problems/guidance";
import { MAX_DECISIONS } from "./ReviewQueuePage";

/** A request written as several lines becomes several checks; one line stays one request (as review.py). */
export function requestedChecks(text: string): string[] | null {
  const lines = text.split("\n").map((line) => line.replace(/^[-*\s]+/, "").trim()).filter(Boolean);
  return lines.length > 1 ? lines : null;
}

export type Decided = "approved" | "requested" | "rejected";

function ApproveDialog({ record, open, onOpenChange, onDecided }: { record: RCARecord; open: boolean; onOpenChange: (open: boolean) => void; onDecided: (decided: Decided) => void }) {
  const { t } = useI18n();
  const report = useReport();
  const apply = useApplyReview();
  const [chosen, setChosen] = useState(record.hypotheses[0]?.hypothesis_id ?? "");
  const [comment, setComment] = useState("");
  useEffect(() => { if (open) { setChosen(record.hypotheses[0]?.hypothesis_id ?? ""); setComment(""); } }, [open, record.hypotheses]);

  const approve = () => apply.mutate({ rcaId: record.rca_id, review: { decision: "APPROVE", comment: comment.trim(), hypothesis_id: chosen } }, {
    onSuccess: () => { onOpenChange(false); onDecided("approved"); },
    onError: (error) => report.failure(error, "review.decision_failed"),
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !apply.isPending && onOpenChange(next)} size="lg" title={t("review.approve_title")} description={t("review.approve_text")}
            footer={<><Button onClick={() => onOpenChange(false)} disabled={apply.isPending}>{t("common.cancel")}</Button>
              <Button variant="primary" icon={<CheckCircle2 className="h-4 w-4" aria-hidden="true" />} onClick={approve} disabled={!chosen} loading={apply.isPending}>{t("review.approve")}</Button></>}>
      <fieldset>
        <legend className="text-sm font-medium text-ink">{t("review.approve_choose")}</legend>
        <div className="mt-2 flex flex-col gap-2">
          {record.hypotheses.map((hypothesis) => (
            <label key={hypothesis.hypothesis_id}
                   className={clsx("flex cursor-pointer gap-3 rounded-card border p-3 transition-colors",
                     chosen === hypothesis.hypothesis_id ? "border-brand-600 bg-brand-50 ring-1 ring-brand-600" : "border-line hover:bg-brand-50/50")}>
              <input type="radio" name="hypothesis" value={hypothesis.hypothesis_id} checked={chosen === hypothesis.hypothesis_id}
                     onChange={() => setChosen(hypothesis.hypothesis_id)} className="mt-1 accent-[rgb(var(--brand-600))]" />
              <span className="min-w-0">
                <span className="flex items-center gap-2"><ConfidencePill confidence={hypothesis.confidence} /><span className="tabular text-xs text-muted">{hypothesis.hypothesis_id}</span></span>
                <span className="mt-1 block text-sm text-ink">{hypothesis.candidate_root_cause}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <TextArea className="mt-4" label={t("review.comment_optional")} hint={t("review.comment_hint")} rows={3} value={comment} onChange={(event) => setComment(event.target.value)} />
    </Dialog>
  );
}

function RequestDialog({ record, open, onOpenChange, onDecided }: { record: RCARecord; open: boolean; onOpenChange: (open: boolean) => void; onDecided: (decided: Decided) => void }) {
  const { t } = useI18n();
  const report = useReport();
  const apply = useApplyReview();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<GuidanceDraft>(() => draftOf(null));
  useEffect(() => { if (open) { setText(""); setError(null); setDraft(draftOf(null)); } }, [open]);
  const number = record.review_rounds + 1; // failed runs do not count: only the decisions of the expert
  const last = number >= MAX_DECISIONS;
  const invalid = Object.values(draftErrors(draft)).some(Boolean);

  const send = () => {
    if (!text.trim()) return setError(t("review.request_required"));
    const guidance = guidanceOf({ ...draft, notes: "", instructions: "" }); // only the wider searches
    const review: ReviewRequest = { decision: "REQUEST_MORE_DETAILS", comment: text.trim(), requested_checks: requestedChecks(text), guidance };
    apply.mutate({ rcaId: record.rca_id, review }, {
      onSuccess: () => { onOpenChange(false); onDecided("requested"); },
      onError: (failure) => report.failure(failure, "review.decision_failed"),
    });
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !apply.isPending && onOpenChange(next)} size="lg" title={t("review.request_title")} description={t("review.request_text")}
            footer={<><Button onClick={() => onOpenChange(false)} disabled={apply.isPending}>{t("common.cancel")}</Button>
              <Button variant="primary" icon={<MessageSquareText className="h-4 w-4" aria-hidden="true" />} onClick={send} disabled={invalid} loading={apply.isPending}>{t("review.request")}</Button></>}>
      <div className="flex flex-col gap-4">
        <p className={clsx("flex items-start gap-2 rounded-control px-3 py-2 text-sm", last ? "bg-warning-soft text-warning" : "bg-neutral-soft text-muted")}>
          {last && <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />}
          {last ? t("review.request_last") : t("review.request_decision", { number, max: MAX_DECISIONS })}
        </p>
        <TextArea label={t("review.request_field")} required rows={4} value={text} placeholder={t("review.request_placeholder")} error={error} autoFocus
                  onChange={(event) => { setText(event.target.value); setError(null); }} />
        <Disclosure label={t("review.request_searches")}>
          <GuidanceForm draft={draft} onChange={setDraft} searchesOnly exclude={record.context?.services ?? []} />
        </Disclosure>
      </div>
    </Dialog>
  );
}

/** The three ways a review can end. Each one calls the real workflow; the page changes only after it succeeded. */
export function ReviewDecisions({ record, onDecided }: { record: RCARecord; onDecided: (decided: Decided) => void }) {
  const { t } = useI18n();
  const report = useReport();
  const apply = useApplyReview();
  const [dialog, setDialog] = useState<"approve" | "request" | "reject" | null>(null);
  const close = (open: boolean) => !open && setDialog(null);

  return (
    <Card className="border-brand-600/30 p-5 sm:p-6">
      <h2 className="text-lg font-semibold text-ink">{t("review.decide_title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("review.decide_text")}</p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <Button variant="primary" icon={<CheckCircle2 className="h-4 w-4" aria-hidden="true" />} onClick={() => setDialog("approve")} disabled={record.hypotheses.length === 0}>{t("review.approve")}</Button>
        <Button icon={<MessageSquareText className="h-4 w-4" aria-hidden="true" />} onClick={() => setDialog("request")}>{t("review.request")}</Button>
        <Button variant="danger-ghost" icon={<XCircle className="h-4 w-4" aria-hidden="true" />} onClick={() => setDialog("reject")}>{t("review.reject")}</Button>
      </div>
      <ApproveDialog record={record} open={dialog === "approve"} onOpenChange={close} onDecided={onDecided} />
      <RequestDialog record={record} open={dialog === "request"} onOpenChange={close} onDecided={onDecided} />
      <ConfirmDialog
        open={dialog === "reject"}
        onOpenChange={close}
        title={t("review.reject_title")}
        description={t("review.reject_text")}
        confirmLabel={t("review.reject")}
        tone="danger"
        reason={{ label: t("review.reject_reason"), required: true, requiredMessage: t("problem.reason_required") }}
        onConfirm={(reason) => apply.mutateAsync({ rcaId: record.rca_id, review: { decision: "REJECT", comment: reason } }).then(
          () => onDecided("rejected"),
          (error: unknown) => { report.failure(error, "review.decision_failed"); throw error; },
        )}
      />
    </Card>
  );
}
