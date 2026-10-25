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
  const { t } = useI18n();
  return <Pill tone={PRIORITY_TONE[priority] ?? "neutral"}>{t(`priority.${priority}`)}</Pill>;
}

export function SeverityPill({ severity }: { severity: Severity }) {
  const { t } = useI18n();
  return <Pill tone={SEVERITY_TONE[severity] ?? "neutral"}>{t(`severity.${severity}`)}</Pill>;
}

export function ConfidencePill({ confidence }: { confidence: Confidence }) {
  const { t } = useI18n();
  return <Pill tone={CONFIDENCE_TONE[confidence] ?? "neutral"}>{t(`confidence.${confidence}`)}</Pill>;
}

// the server proposes incidents together from 0.85 (rca/suggestions.TEXT_ALIKE_SAME_CI); "very" is clearly above
const VERY_ALIKE = 0.92;
const ALIKE = 0.85;

export type SimilarityLevel = "very" | "alike" | "slight";

/** A 0–1 text similarity in words, instead of a percentage that reads like a probability. */
export function similarityLevel(score: number): SimilarityLevel {
  return score >= VERY_ALIKE ? "very" : score >= ALIKE ? "alike" : "slight";
}

export const SIMILARITY_MIN: Record<Exclude<SimilarityLevel, "slight">, number> = { very: VERY_ALIKE, alike: ALIKE };

const LEVEL_TONE: Record<SimilarityLevel, Tone> = { very: "brand", alike: "info", slight: "neutral" };

export function SimilarityPill({ score, className }: { score: number; className?: string }) {
  const { t } = useI18n();
  const level = similarityLevel(score);
  return <Pill tone={LEVEL_TONE[level]} className={className}>{t(`similarity.${level}`)}</Pill>;
}
