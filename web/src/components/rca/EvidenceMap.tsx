import { clsx } from "clsx";
import type { Evidence, EvidenceType, Hypothesis } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { ConfidencePill } from "@/components/ui/Pills";
import { NODE } from "./FiveWhysDiagram";

const CONFIDENCE_BOX: Record<Hypothesis["confidence"], string> = {
  HIGH: "border-[#2E9B5B] bg-[#DDF3E4]",
  MEDIUM: "border-[#E8891C] bg-[#FFF3E2]",
  LOW: "border-[#9AA8A4] bg-[#F3F5F4]",
};

function Group({ items, against }: { items: Evidence[]; against: boolean }) {
  const { t } = useI18n();
  const byType = new Map<EvidenceType, Evidence[]>();
  items.forEach((item) => byType.set(item.type, [...(byType.get(item.type) ?? []), item]));
  return (
    <div className="flex flex-col gap-1.5">
      {[...byType.entries()].map(([type, list]) => (
        <div key={type} className={clsx("rounded-[10px] border-2 bg-surface px-2.5 py-1.5 shadow-card", against ? "border-dashed border-[#D9534F]/70" : "border-[#7C5CCB]/50")}>
          <p className={clsx("text-[10px] font-bold uppercase tracking-wide", against ? "text-[#B5352F]" : "text-[#4C2F96]")}>{t(`evidence.type.${type}`)} · {list.length}</p>
          <p className="mt-0.5 flex flex-wrap gap-1">
            {list.map((item) => <span key={item.evidence_id} title={item.description} className="tabular text-[11px] text-ink">{item.citation}</span>)}
          </p>
        </div>
      ))}
    </div>
  );
}

/** How the findings connect: the problem, each candidate cause (coloured by its confidence) and the evidence
 * it cites, for it (solid) and against it (dashed), grouped by type. Every box is a stored record. */
export function EvidenceMap({ problem, hypotheses, evidence }: { problem: string; hypotheses: Hypothesis[]; evidence: Evidence[] }) {
  const { t } = useI18n();
  const known = new Map(evidence.map((item) => [item.evidence_id, item]));
  const cited = (ids: string[]) => ids.map((id) => known.get(id)).filter((item): item is Evidence => Boolean(item));

  return (
    <div className="flex w-[880px] items-center gap-0 py-2">
      <div className={clsx("w-[180px] shrink-0 rounded-[18px] border-2 px-4 py-4 text-center text-sm font-semibold leading-snug shadow-card animate-fade-up", NODE.problem)}>
        {problem}
      </div>
      <div className="relative flex flex-1 flex-col gap-5 border-l-2 border-[#B9C3C0] py-2 pl-0">
        {hypotheses.map((hypothesis, index) => {
          const supporting = cited(hypothesis.supporting_evidence);
          const contradicting = cited(hypothesis.contradicting_evidence);
          return (
            <div key={hypothesis.hypothesis_id} className="flex items-center animate-fade-up" style={{ animationDelay: `${(index + 1) * 140}ms` }}>
              <span className="h-0.5 w-6 shrink-0 bg-[#B9C3C0]" aria-hidden="true" />
              <div className={clsx("w-[280px] shrink-0 rounded-[12px] border-2 p-3 shadow-card", CONFIDENCE_BOX[hypothesis.confidence])}>
                <div className="flex items-center justify-between gap-2">
                  <span className="tabular text-[11px] font-bold text-muted">{hypothesis.hypothesis_id}</span>
                  <ConfidencePill confidence={hypothesis.confidence} />
                </div>
                <p className="mt-1.5 line-clamp-4 text-xs leading-snug text-ink" title={hypothesis.candidate_root_cause}>{hypothesis.candidate_root_cause}</p>
              </div>
              <div className="flex flex-1 flex-col gap-2 pl-0">
                {[{ list: supporting, against: false }, { list: contradicting, against: true }].filter((lane) => lane.list.length > 0).map((lane) => (
                  <div key={String(lane.against)} className="flex items-center">
                    <span className={clsx("w-8 shrink-0 border-t-2", lane.against ? "border-dashed border-[#D9534F]/70" : "border-[#7C5CCB]/60")} aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <p className={clsx("mb-1 text-[10px] font-bold uppercase", lane.against ? "text-[#B5352F]" : "text-[#4C2F96]")}>{lane.against ? t("diagram.against") : t("diagram.for")}</p>
                      <Group items={lane.list} against={lane.against} />
                    </div>
                  </div>
                ))}
                {supporting.length + contradicting.length === 0 && <p className="pl-8 text-xs text-muted">{t("diagram.no_evidence")}</p>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
