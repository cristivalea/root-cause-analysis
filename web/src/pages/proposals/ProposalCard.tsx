import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, FileSearch, History, Info, Layers, Lightbulb, Plus, X } from "lucide-react";
import { useAcceptProposal, useRejectProposal } from "@/api/queries";
import type { Incident, Proposal } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Button, IconButton } from "@/components/ui/Button";
import { Card, Id } from "@/components/ui/Card";
import { ConfirmDialog, Dialog } from "@/components/ui/Dialog";
import { Disclosure } from "@/components/ui/Disclosure";
import { TextArea, TextInput } from "@/components/ui/Field";
import { SimilarityPill } from "@/components/ui/Pills";
import { useReport } from "@/lib/useReport";
import { proposalTexts } from "./notes";

/** What an accepted proposal made, for the confirmation the page shows. */
export interface ProposalDone {
  kind: "created" | "attached";
  problem: string;
  incident?: string;
  already: boolean;
  warnings: string[];
}

function CreateDialog({ proposal, open, onOpenChange, onDone }: { proposal: Proposal; open: boolean; onOpenChange: (open: boolean) => void; onDone: (done: ProposalDone) => void }) {
  const { t } = useI18n();
  const report = useReport();
  const accept = useAcceptProposal();
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  useEffect(() => { if (open) { setTitle(""); setReason(""); } }, [open]);

  const create = () =>
    accept.mutate({ proposal, title: title.trim(), reason: reason.trim() }, {
      onSuccess: (result) => {
        onOpenChange(false);
        onDone({ kind: "created", problem: result.problem.problem_id, already: !result.created, warnings: result.warnings });
      },
      onError: (error) => report.failure(error),
    });

  return (
    <Dialog open={open} onOpenChange={(next) => !accept.isPending && onOpenChange(next)}
            title={t("proposals.create_title", { count: proposal.incident_ids.length })} description={t("proposals.create_text")}
            footer={<>
              <Button onClick={() => onOpenChange(false)} disabled={accept.isPending}>{t("common.cancel")}</Button>
              <Button variant="primary" onClick={create} loading={accept.isPending}>{t("proposals.create")}</Button>
            </>}>
      <div className="flex flex-col gap-4">
        <TextInput label={t("proposals.title_input")} hint={t("proposals.title_hint")} value={title} autoFocus
                   onChange={(event) => setTitle(event.target.value)} maxLength={200} />
        <TextArea label={t("proposals.reason_create")} hint={t("proposals.reason_hint")} rows={3} value={reason}
                  onChange={(event) => setReason(event.target.value)} />
      </div>
    </Dialog>
  );
}

/** One proposal as a small card: what it proposes and its similarity at a glance; its incidents, the facts
 * from the sources and the reasons folded underneath, so nothing is lost and nothing crowds the card. */
export function ProposalCard({ proposal, incidents, onDetails, index, onDone }: {
  proposal: Proposal;
  incidents: Map<string, Incident>;
  onDetails: (incidentId: string) => void;
  index: number;
  onDone: (done: ProposalDone) => void;
}) {
  const { t, language } = useI18n();
  const report = useReport();
  const accept = useAcceptProposal();
  const said = proposalTexts(proposal, t, language);
  const reject = useRejectProposal();
  const [creating, setCreating] = useState(false);
  const [adding, setAdding] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const first = proposal.incident_ids[0] ?? "";
  const services = [...new Set(proposal.incident_ids.map((id) => incidents.get(id)?.service).filter(Boolean))] as string[];

  const title = proposal.kind === "group"
    ? t("proposals.group_title", { count: proposal.incident_ids.length })
    : proposal.kind === "attach"
      ? t("proposals.attach_title", { incident: first, problem: proposal.problem_id ?? "" })
      : t("proposals.single_title", { incident: first });

  return (
    <Card className="p-4 transition-shadow duration-150 hover:shadow-pop animate-fade-up sm:p-5" style={{ animationDelay: `${index * 50}ms` }}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-ink">{title}</h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {services.map((service) => (
              <span key={service} className="rounded-full bg-neutral-soft px-2 py-0.5 text-xs font-medium text-muted">{service}</span>
            ))}
            {proposal.kind === "attach" && proposal.problem_id && (
              <Link to={`/problems/${proposal.problem_id}`} className="text-xs font-semibold text-brand-700 hover:underline">{proposal.problem_id}</Link>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">{t("proposals.similarity")}</span>
          {proposal.score !== null
            ? <SimilarityPill score={proposal.score} />
            : <span className="text-xs text-muted">{t("proposals.no_score")}</span>}
        </div>
      </div>

      {proposal.recurrence_of && (
        <p className="mt-3 flex items-center gap-2 rounded-control bg-warning-soft px-3 py-2 text-sm text-warning">
          <History className="h-4 w-4 shrink-0" aria-hidden="true" />{t("proposals.recurrence", { problem: proposal.recurrence_of })}
        </p>
      )}

      <div className="mt-3 flex flex-col gap-1 border-t border-line pt-3">
        <Disclosure label={t("proposals.incidents")} count={proposal.incident_ids.length} defaultOpen={proposal.kind !== "group"}
                    icon={<Layers className="h-4 w-4" aria-hidden="true" />}>
          <ul className="flex flex-col gap-1">
            {proposal.incident_ids.map((id) => (
              <li key={id} className="flex items-center gap-3 rounded-control px-2 py-1.5 hover:bg-brand-50/60">
                <Id>{id}</Id>
                <span className="min-w-0 flex-1 truncate text-sm text-ink">{incidents.get(id)?.title}</span>
                <IconButton label={t("problem.details", { id })} onClick={() => onDetails(id)}>
                  <Info className="h-4 w-4" aria-hidden="true" />
                </IconButton>
              </li>
            ))}
          </ul>
        </Disclosure>
        {said.evidence.length > 0 && (
          <Disclosure label={t("proposals.sources")} icon={<FileSearch className="h-4 w-4" aria-hidden="true" />}>
            <ul className="flex flex-col gap-1.5 pl-1">
              {said.evidence.map((fact) => (
                <li key={fact} className="flex gap-2 rounded-control bg-[#EEE7FB]/60 px-3 py-1.5 text-sm text-ink">
                  <FileSearch className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#7C5CCB]" aria-hidden="true" />{fact}
                </li>
              ))}
            </ul>
          </Disclosure>
        )}
        {said.reasons.length > 0 && (
          <Disclosure label={t("proposals.why")} icon={<Lightbulb className="h-4 w-4" aria-hidden="true" />}>
            <ul className="list-disc space-y-1 pl-6 text-sm text-muted">
              {said.reasons.map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          </Disclosure>
        )}
      </div>

      <div className="mt-4 flex flex-wrap justify-end gap-2">
        {proposal.kind !== "single" && (
          <Button size="sm" variant="danger-ghost" icon={<X className="h-4 w-4" aria-hidden="true" />} onClick={() => setRejecting(true)}>
            {t("proposals.reject")}
          </Button>
        )}
        {proposal.kind === "attach" ? (
          <Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" aria-hidden="true" />} onClick={() => setAdding(true)}>
            {t("proposals.add")}
          </Button>
        ) : (
          <Button size="sm" variant="primary" icon={<Check className="h-4 w-4" aria-hidden="true" />} onClick={() => setCreating(true)}>
            {t("proposals.create")}
          </Button>
        )}
      </div>

      {proposal.kind !== "attach" && <CreateDialog proposal={proposal} open={creating} onOpenChange={setCreating} onDone={onDone} />}
      <ConfirmDialog
        open={adding}
        onOpenChange={setAdding}
        title={t("proposals.add_title", { incident: first, problem: proposal.problem_id ?? "" })}
        description={t("proposals.add_text")}
        confirmLabel={t("proposals.add")}
        reason={{ label: t("problem.reason_optional"), required: false, requiredMessage: "" }}
        onConfirm={(reason) => accept.mutateAsync({ proposal, reason }).then(
          (result) => onDone({ kind: "attached", problem: result.problem.problem_id, incident: first, already: !result.created, warnings: result.warnings }),
          (error: unknown) => { report.failure(error); throw error; },
        )}
      />
      <ConfirmDialog
        open={rejecting}
        onOpenChange={setRejecting}
        title={t("proposals.reject_title")}
        description={t("proposals.reject_text")}
        confirmLabel={t("proposals.reject")}
        tone="danger"
        reason={{ label: t("proposals.reject_reason"), required: true, requiredMessage: t("problem.reason_required") }}
        onConfirm={(reason) => reject.mutateAsync({ proposal, reason }).then(
          () => report.success(t("proposals.rejected")),
          (error: unknown) => { report.failure(error); throw error; },
        )}
      />
    </Card>
  );
}
