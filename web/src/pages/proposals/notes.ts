import type { Note, ProblemStatus, Proposal, Severity } from "@/api/types";
import type { Language, Translate } from "@/i18n/I18nProvider";
import { formatDate } from "@/lib/format";
import { similarityLevel } from "@/components/ui/Pills";

const SEVERITIES: Severity[] = ["SEV-1", "SEV-2", "SEV-3", "SEV-4"];
const PROBLEM_STATUSES: ProblemStatus[] = ["Open", "In investigation", "Manual", "Closed"];

const text = (value: unknown) => (value === null || value === undefined ? "" : String(value));
const list = (value: unknown) => (Array.isArray(value) ? value.map(text).join(", ") : text(value));

function severity(value: unknown, t: Translate) {
  return SEVERITIES.includes(value as Severity) ? t(`severity.${value as Severity}`).toLowerCase() : text(value);
}

function problemStatus(value: unknown, t: Translate) {
  return PROBLEM_STATUSES.includes(value as ProblemStatus) ? t(`status.problem.${value as ProblemStatus}`).toLowerCase() : text(value);
}

/** One reason or fact of a proposal (rca/suggestions.Note) in plain words, in the language of the interface.
 * A code this version does not know yet gives null: the caller shows the English sentence instead. */
export function noteText(note: Note, t: Translate, language: Language): string | null {
  const p = note.params;
  switch (note.code) {
    case "same_service": return t("note.same_service", { service: text(p.service) });
    case "same_ci": return t("note.same_ci", { incident: text(p.incident), ci: text(p.ci) });
    case "text_alike":
      return t(similarityLevel(Number(p.similarity)) === "very" ? "note.text_very_alike" : "note.text_alike",
        { incident: text(p.incident), title: text(p.title) });
    case "same_errors": return t("note.same_errors", { types: list(p.types) });
    case "days_apart": {
      const days = Number(p.days);
      return days === 0 ? t("note.same_day", { incident: text(p.incident) })
        : days === 1 ? t("note.one_day", { incident: text(p.incident) })
          : t("note.days_apart", { incident: text(p.incident), days });
    }
    case "more_alike":
      return Number(p.count) === 1 ? t("note.one_more", { incidents: list(p.incidents) })
        : t("note.more_alike", { count: text(p.count), incidents: list(p.incidents) + (Number(p.count) > 3 ? "…" : "") });
    case "closed_problem": return t("note.closed_problem", { problem: text(p.problem) });
    case "busy_problem": return t("note.busy_problem", { problem: text(p.problem), status: problemStatus(p.status, t) });
    case "group": return t("note.group", { count: text(p.count), service: text(p.service) });
    case "looks_like_closed": return t("note.looks_like_closed", { problem: text(p.problem) });
    case "group_rejected":
      return t("note.group_rejected", { incidents: list(p.incidents) + (Number(p.more) > 0 ? "…" : "") });
    case "attach_rejected": return t("note.attach_rejected", { problem: text(p.problem) });
    case "major":
      return p.reason ? t("note.major_because", { severity: severity(p.severity, t), reason: text(p.reason) })
        : t("note.major", { severity: severity(p.severity, t) });
    case "alone": return t("note.alone", { severity: severity(p.severity, t) });
    case "looks_like_busy": return t("note.looks_like_busy", { problem: text(p.problem), status: problemStatus(p.status, t) });
    case "ci_count": return t("note.ci_count", { ci: text(p.ci), count: text(p.count), total: text(p.total) });
    case "error_types": {
      const types = Array.isArray(p.types) ? (p.types as { type?: unknown; count?: unknown }[]) : [];
      return t("note.error_types", { types: types.map((item) => `${text(item.type)} (${text(item.count)})`).join(", ") });
    }
    case "severities": {
      const counts = typeof p.counts === "object" && p.counts !== null ? (p.counts as Record<string, unknown>) : {};
      return t("note.severities", { list: Object.entries(counts).map(([key, count]) => `${severity(key, t)}: ${text(count)}`).join(", ") });
    }
    case "detected": {
      const first = formatDate(text(p.first), language);
      const last = formatDate(text(p.last), language);
      return first === last ? t("note.detected_one", { first }) : t("note.detected", { first, last });
    }
    default: return null;
  }
}

/** The reasons and the facts of a proposal in plain words; an older server without notes keeps its sentences. */
export function proposalTexts(proposal: Proposal, t: Translate, language: Language) {
  const say = (notes: Note[] | undefined, fallback: string[]) =>
    notes && notes.length === fallback.length ? notes.map((note, index) => noteText(note, t, language) ?? fallback[index]!) : fallback;
  return { reasons: say(proposal.reason_notes, proposal.reasons), evidence: say(proposal.evidence_notes, proposal.evidence) };
}
