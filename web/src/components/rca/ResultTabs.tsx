import { useMemo, useState, type ReactNode } from "react";
import { clsx } from "clsx";
import { AlertTriangle, CheckCircle2, CircleHelp, PenLine, ShieldCheck, Sparkles, Wrench } from "lucide-react";
import { useDiagram } from "@/api/queries";
import { revisionId, type Evidence, type EvidenceType, type RCARecord } from "@/api/types";
import { useI18n, type Translate } from "@/i18n/I18nProvider";
import type { MessageKey } from "@/i18n/en";
import { Card, Id } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { PillTabs } from "@/components/ui/PillTabs";
import { ConfidencePill, Pill } from "@/components/ui/Pills";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { evidenceSummary } from "@/lib/evidence";
import { formatDateTime } from "@/lib/format";
import { DiagramFrame } from "./DiagramFrame";
import { EvidenceChip, TYPE_TONE } from "./EvidenceChip";
import { FishboneDiagram } from "./FishboneDiagram";
import { FiveWhysDiagram } from "./FiveWhysDiagram";

export type ResultTab = "causes" | "summary" | "evidence" | "not_verified" | "timeline" | "checks" | "cause_diagram" | "steps";

const TAB_LABEL: Record<ResultTab, MessageKey> = {
  causes: "tabs.causes", summary: "tabs.summary", evidence: "tabs.evidence", not_verified: "tabs.not_verified",
  timeline: "tabs.timeline", checks: "tabs.checks", cause_diagram: "tabs.cause_diagram", steps: "tabs.steps",
};

function Heading({ children }: { children: ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-wide text-muted">{children}</p>;
}

function Bullets({ items }: { items: string[] }) {
  return <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-relaxed text-ink">{items.map((item, index) => <li key={index}>{item}</li>)}</ul>;
}

/** The evidence of a diagram node as people read it ("Change: Deploy auth-service…"), shorter than in the cards. */
function evidenceLabel(record: RCARecord, t: Translate) {
  const known = new Map(record.evidence.map((item) => [item.evidence_id, item]));
  return (ids: string[]) => ids.map((id) => {
    const item = known.get(id);
    return { id, label: item ? `${t(`evidence.type.${item.type}`)}: ${evidenceSummary(item, 40)}` : id };
  });
}

// ----------------------------------------------------------------------------------- the tabs

function Causes({ record }: { record: RCARecord }) {
  const { t } = useI18n();
  const known = new Map(record.evidence.map((item) => [item.evidence_id, item]));
  const cited = (ids: string[]) => ids.map((id) => known.get(id)).filter((item): item is Evidence => Boolean(item));
  if (record.hypotheses.length === 0) return <EmptyState title={t("causes.none")} />;
  return (
    <div className="flex flex-col gap-4">
      <p className="flex items-start gap-2 rounded-card bg-info-soft px-4 py-3 text-sm text-info"><Sparkles className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />{t("causes.note")}</p>
      {record.weakly_supported && <p className="flex items-start gap-2 rounded-card bg-warning-soft px-4 py-3 text-sm text-warning"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />{t("causes.weak")}</p>}
      {record.single_hypothesis_reason && <p className="text-sm text-muted">{t("causes.single_reason", { reason: record.single_hypothesis_reason })}</p>}
      {record.hypotheses.map((hypothesis, index) => (
        <Card key={hypothesis.hypothesis_id} className={clsx("p-5", index === 0 && "border-brand-600/40 ring-1 ring-brand-600/20")}>
          <div className="flex flex-wrap items-center gap-2">
            <ConfidencePill confidence={hypothesis.confidence} />
            <span className="tabular text-xs text-muted">{t("causes.points", { points: hypothesis.confidence_points })}</span>
            <span className="tabular text-xs text-muted">{hypothesis.hypothesis_id}</span>
            {index === 0 && <Pill tone="brand">{t("causes.main")}</Pill>}
          </div>
          <p className="mt-3 text-[15px] font-semibold leading-snug text-ink">{hypothesis.candidate_root_cause}</p>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <Heading>{t("causes.supported")}</Heading>
              <div className="mt-1.5 flex flex-wrap gap-1">{cited(hypothesis.supporting_evidence).map((item) => <EvidenceChip key={item.evidence_id} item={item} />)}{hypothesis.supporting_evidence.length === 0 && <span className="text-sm text-muted">—</span>}</div>
            </div>
            <div>
              <Heading>{t("causes.contradicted")}</Heading>
              <div className="mt-1.5 flex flex-wrap gap-1">{cited(hypothesis.contradicting_evidence).map((item) => <EvidenceChip key={item.evidence_id} item={item} />)}{hypothesis.contradicting_evidence.length === 0 && <span className="text-sm text-muted">—</span>}</div>
            </div>
          </div>
          <div className="mt-4 flex flex-col gap-1 border-t border-line pt-3">
            {hypothesis.reasons.length > 0 && (
              <Disclosure label={t("causes.why")} icon={<PenLine className="h-4 w-4" aria-hidden="true" />}>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">{t("causes.generated")}</p>
                <Bullets items={hypothesis.reasons} />
              </Disclosure>
            )}
            {hypothesis.missing_evidence.length > 0 && (
              <Disclosure label={t("causes.missing")} icon={<CircleHelp className="h-4 w-4" aria-hidden="true" />}><Bullets items={hypothesis.missing_evidence} /></Disclosure>
            )}
            {hypothesis.recommended_validation.length > 0 && (
              <Disclosure label={t("causes.validate")} icon={<CheckCircle2 className="h-4 w-4" aria-hidden="true" />}><Bullets items={hypothesis.recommended_validation} /></Disclosure>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}

function Summary({ record }: { record: RCARecord }) {
  const { t } = useI18n();
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <Card className="p-5">
        <Heading>{t("summary.title")}</Heading>
        <p className="mt-2 text-[15px] leading-relaxed text-ink">{record.investigation_summary || "—"}</p>
        {record.observed_patterns.length > 0 && <div className="mt-4"><Heading>{t("summary.patterns")}</Heading><Bullets items={record.observed_patterns} /></div>}
        {record.linked_incidents.length > 0 && <div className="mt-4"><Heading>{t("summary.related")}</Heading><p className="mt-1 flex flex-wrap gap-2">{record.linked_incidents.map((id) => <Id key={id}>{id}</Id>)}</p></div>}
      </Card>
      <Card className="border-success/30 bg-success-soft/40 p-5">
        <p className="flex items-center gap-2 font-semibold text-ink"><Wrench className="h-4 w-4 text-success" aria-hidden="true" />{t("summary.workaround")}</p>
        <p className="mt-2 text-sm leading-relaxed text-ink">{record.suggested_workaround || t("summary.no_workaround")}</p>
        {record.change_likely_required && <p className="mt-3 rounded-control bg-surface px-3 py-2 text-sm text-warning">{t("summary.change")}</p>}
      </Card>
    </div>
  );
}

function EvidenceList({ record }: { record: RCARecord }) {
  const { t, language } = useI18n();
  const types = [...new Set(record.evidence.map((item) => item.type))];
  const [type, setType] = useState<EvidenceType | "all">("all");
  if (record.evidence.length === 0) return <EmptyState title={t("evidence.none")} />;
  const shown = type === "all" ? record.evidence : record.evidence.filter((item) => item.type === type);
  return (
    <div>
      <div role="group" aria-label={t("evidence.filter")} className="flex flex-wrap gap-1.5">
        {(["all", ...types] as const).map((item) => (
          <button key={item} type="button" aria-pressed={type === item} onClick={() => setType(item)}
                  className={clsx("h-8 rounded-full border px-3 text-xs font-semibold transition-colors",
                    type === item ? "border-brand-600 bg-brand-600 text-white" : "border-line bg-surface text-muted hover:text-ink")}>
            {item === "all" ? t("common.all") : t(`evidence.type.${item}`)} · {item === "all" ? record.evidence.length : record.evidence.filter((entry) => entry.type === item).length}
          </button>
        ))}
      </div>
      <ul className="mt-4 grid gap-2 lg:grid-cols-2">
        {shown.map((item) => (
          <li key={item.evidence_id} className="rounded-card border border-line bg-surface p-3.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="tabular text-xs font-bold text-muted">{item.evidence_id}</span>
              <span className={clsx("rounded-full px-2 py-0.5 text-[11px] font-semibold", TYPE_TONE[item.type])}>{t(`evidence.type.${item.type}`)}</span>
              <Id>{item.citation}</Id>
              {item.timestamp && <span className="ml-auto text-xs text-muted">{formatDateTime(item.timestamp, language)}</span>}
            </div>
            <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-ink" title={item.description}>{item.description}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function NotVerified({ record }: { record: RCARecord }) {
  const { t } = useI18n();
  return (
    <div>
      <p className="text-sm text-muted">{t("notverified.text")}</p>
      {record.not_checked.length === 0 ? <p className="mt-4 text-sm text-muted">{t("notverified.none")}</p> : (
        <ul className="mt-4 flex flex-col gap-2">
          {record.not_checked.map((item, index) => (
            <li key={index} className="flex gap-3 rounded-card border border-dashed border-warning/40 bg-warning-soft/40 px-4 py-3 text-sm text-ink">
              <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />{item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const MARKER_TONE: Record<string, string> = {
  "first error": "bg-danger text-white", "incident detected": "bg-info text-white",
  "before the first error": "bg-warning-soft text-warning", "after the first error": "bg-neutral-soft text-muted",
};

function Timeline({ record }: { record: RCARecord }) {
  const { t, language } = useI18n();
  const [all, setAll] = useState(false);
  if (record.timeline.length === 0) return <EmptyState title={t("timeline.none")} />;
  const shown = all ? record.timeline : record.timeline.slice(0, 25);
  return (
    <div>
      <p className="text-sm text-muted">{t("timeline.text")}</p>
      <ol className="relative mt-4 border-l-2 border-line pl-6">
        {shown.map((entry, index) => (
          <li key={`${entry.evidence_id}-${index}`} className="relative pb-4 last:pb-0">
            <span aria-hidden="true" className={clsx("absolute -left-[33px] top-1 h-4 w-4 rounded-full border-[3px] border-surface", entry.marker === "first error" ? "bg-danger" : TYPE_TONE[entry.type].split(" ")[0])} />
            <div className="flex flex-wrap items-center gap-2">
              <span className="tabular text-xs font-semibold text-ink">{formatDateTime(entry.at, language)}</span>
              <span className={clsx("rounded-full px-2 py-0.5 text-[11px] font-semibold", TYPE_TONE[entry.type])}>{t(`evidence.type.${entry.type}`)}</span>
              <Id>{entry.citation}</Id>
              {entry.marker && <span className={clsx("rounded-full px-2 py-0.5 text-[11px] font-bold", MARKER_TONE[entry.marker] ?? "bg-neutral-soft text-muted")}>
                {["first error", "before the first error", "after the first error", "incident detected"].includes(entry.marker) ? t(`timeline.marker.${entry.marker}` as MessageKey) : entry.marker}
              </span>}
            </div>
            <p className="mt-1 text-sm leading-relaxed text-ink">{entry.what}</p>
          </li>
        ))}
      </ol>
      {record.timeline.length > 25 && !all && (
        <button type="button" onClick={() => setAll(true)} className="mt-3 text-sm font-semibold text-brand-700 hover:underline">{t("timeline.show_all", { count: record.timeline.length })}</button>
      )}
    </div>
  );
}

function Checks({ record }: { record: RCARecord }) {
  const { t } = useI18n();
  const runs = record.trace.filter((step) => step.name === "guardrail");
  const last = runs[runs.length - 1];
  const problems = (last?.details?.problems as string[] | undefined) ?? [];
  const warnings = (last?.details?.warnings as string[] | undefined) ?? [];
  return (
    <div className="flex flex-col gap-4">
      <Card className="p-5">
        <p className="flex items-center gap-2 font-semibold text-ink"><ShieldCheck className="h-5 w-5 text-brand-600" aria-hidden="true" />{t("checks.title")}</p>
        <p className="mt-1 text-sm text-muted">{t("checks.text")}</p>
        {!last ? <p className="mt-3 text-sm text-muted">{t("checks.none")}</p> : (
          <div className="mt-4 flex flex-col gap-3">
            <p className="flex items-center gap-2 text-sm font-medium text-ink"><CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />{last.summary}</p>
            {problems.length > 0 && <div><Heading>{t("step.problems")}</Heading><Bullets items={problems} /></div>}
            {warnings.length > 0 && <Disclosure label={`${t("step.warnings")} (${warnings.length})`}><Bullets items={warnings} /></Disclosure>}
          </div>
        )}
      </Card>
      <Card className="p-5">
        <p className="font-semibold text-ink">{t("checks.confidence_title")}</p>
        <p className="mt-1 text-sm text-muted">{t("checks.confidence_text")}</p>
        <ul className="mt-3 flex flex-col gap-3">
          {record.hypotheses.map((hypothesis) => (
            <li key={hypothesis.hypothesis_id}>
              <div className="flex items-center gap-2"><span className="tabular text-xs font-bold text-muted">{hypothesis.hypothesis_id}</span><ConfidencePill confidence={hypothesis.confidence} /></div>
              <Bullets items={hypothesis.confidence_reasons} />
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

/** The cause diagram of rca/diagram.py (GET /rcas/{id}/diagram), drawn in the mymap.ai style. */
export function CauseDiagram({ record, problem }: { record: RCARecord; problem: string }) {
  const { t } = useI18n();
  const id = revisionId(record);
  const diagram = useDiagram(id, record.run_status === "COMPLETED");
  const labels = evidenceLabel(record, t);
  if (diagram.isPending) return <Skeleton className="h-80 rounded-card" />;
  if (diagram.isError) return <ErrorState error={diagram.error} title={t("diagram.unavailable")} onRetry={() => void diagram.refetch()} />;
  if (!diagram.data) return <EmptyState title={t("diagram.none")} />;
  const data = diagram.data;
  const hypothesis = record.hypotheses.find((item) => item.hypothesis_id === data.hypothesis_id);
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Pill tone="brand">{data.kind === "five_whys" ? t("diagram.five_whys") : t("diagram.fishbone")}</Pill>
        <span className="text-sm text-muted">{data.kind === "five_whys" ? t("diagram.chosen_five") : t("diagram.chosen_fish")}</span>
      </div>
      <DiagramFrame label={t("diagram.label_cause")} maxHeight={560} className="bg-surface">
        {data.kind === "five_whys" ? (
          <FiveWhysDiagram
            problem={problem}
            steps={data.steps.map((step) => ({ text: step.because, evidence: labels(step.evidence) }))}
            root={record.final_root_cause ?? hypothesis?.candidate_root_cause}
            rootLabel={record.final_root_cause ? t("diagram.root_cause") : t("causes.main")}
          />
        ) : (
          <FishboneDiagram problem={problem} factors={data.factors.map((factor) => ({ ...factor, evidenceLabels: labels(factor.evidence) }))} />
        )}
      </DiagramFrame>
    </div>
  );
}

/** The parts of an analysis as rounded tabs; which ones, and in which order, is the page's choice. */
export function ResultTabs({ record, problem, tabs, steps, defaultTab }: {
  record: RCARecord;
  problem: string;
  tabs: ResultTab[];
  steps?: ReactNode;
  defaultTab?: ResultTab;
}) {
  const { t } = useI18n();
  const [tab, setTab] = useState<ResultTab>(defaultTab ?? tabs[0]!);
  const count: Partial<Record<ResultTab, number>> = useMemo(() => ({
    causes: record.hypotheses.length, evidence: record.evidence.length, not_verified: record.not_checked.length, timeline: record.timeline.length,
  }), [record]);
  const body: Record<ResultTab, ReactNode> = {
    causes: <Causes record={record} />, summary: <Summary record={record} />,
    evidence: <EvidenceList record={record} />, not_verified: <NotVerified record={record} />, timeline: <Timeline record={record} />,
    checks: <Checks record={record} />, cause_diagram: <CauseDiagram record={record} problem={problem} />,
    steps,
  };
  return (
    <PillTabs label={t("tabs.label")} value={tab} onChange={setTab}
              tabs={tabs.map((item) => ({ value: item, label: t(TAB_LABEL[item]), count: count[item] }))}>
      {body[tab]}
    </PillTabs>
  );
}
