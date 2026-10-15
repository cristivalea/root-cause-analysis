import { clsx } from "clsx";
import { useI18n } from "@/i18n/I18nProvider";
import type { Confidence, Priority, ProblemStatus, RCAStatus, Severity } from "@/api/types";

export type Tone = "info" | "warning" | "danger" | "success" | "neutral" | "brand";

const TONES: Record<Tone, string> = {
  info: "bg-info-soft text-info",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  success: "bg-success-soft text-success",
  neutral: "bg-neutral-soft text-muted",
  brand: "bg-brand-100 text-brand-800",
};

/** A short label in a coloured pill. The text always says what the colour says. */
export function Pill({ tone, children, dot = false, className }: { tone: Tone; children: React.ReactNode; dot?: boolean; className?: string }) {
  return (
    <span className={clsx("inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-semibold", TONES[tone], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  );
}

const PROBLEM_TONE: Record<ProblemStatus, Tone> = { Open: "info", "In investigation": "warning", Manual: "danger", Closed: "neutral" };
const RCA_TONE: Record<RCAStatus, Tone> = {
  DRAFT: "info", AWAITING_TECHNICAL_REVIEW: "warning", REQUEST_MORE_DETAILS: "warning", VALIDATED: "success",
  REJECTED: "danger", FAILED: "danger", ESCALATED_MANUAL: "danger",
};
const PRIORITY_TONE: Record<Priority, Tone> = { P1: "danger", P2: "warning", P3: "info", P4: "neutral" };
const SEVERITY_TONE: Record<Severity, Tone> = { "SEV-1": "danger", "SEV-2": "warning", "SEV-3": "info", "SEV-4": "neutral" };
const CONFIDENCE_TONE: Record<Confidence, Tone> = { HIGH: "success", MEDIUM: "warning", LOW: "neutral" };

export function ProblemStatusPill({ status }: { status: ProblemStatus }) {
  const { t } = useI18n();
  return <Pill tone={PROBLEM_TONE[status] ?? "neutral"} dot>{t(`status.problem.${status}`)}</Pill>;
}

export function RcaStatusPill({ status }: { status: RCAStatus }) {
  const { t } = useI18n();
  return <Pill tone={RCA_TONE[status] ?? "neutral"} dot>{t(`status.rca.${status}`)}</Pill>;
}

export function PriorityPill({ priority }: { priority: Priority }) {
  return <Pill tone={PRIORITY_TONE[priority] ?? "neutral"} className="tabular">{priority}</Pill>;
}

export function SeverityPill({ severity }: { severity: Severity }) {
  const { t } = useI18n();
  return <Pill tone={SEVERITY_TONE[severity] ?? "neutral"}>{t(`severity.${severity}`)}</Pill>;
}

export function ConfidencePill({ confidence }: { confidence: Confidence }) {
  const { t } = useI18n();
  return <Pill tone={CONFIDENCE_TONE[confidence] ?? "neutral"}>{t(`confidence.${confidence}`)}</Pill>;
}

/** A 0–1 similarity shown as a percentage with a bar. The stored score is not changed: 0.873 → 87%. */
export function SimilarityBar({ score, label, className }: { score: number; label: string; className?: string }) {
  const percent = Math.round(Math.max(0, Math.min(1, score)) * 100);
  return (
    <div className={clsx("flex items-center gap-2", className)} title={label}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-neutral-soft" role="meter" aria-label={label}
           aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <div className="h-full rounded-full bg-brand-600 transition-[width] duration-500" style={{ width: `${percent}%` }} />
      </div>
      <span className="tabular text-xs font-semibold text-ink">{percent}%</span>
    </div>
  );
}
