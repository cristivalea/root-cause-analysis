import type { ReactNode } from "react";
import { clsx } from "clsx";
import { Bot, Clock3, Cpu } from "lucide-react";
import type { InvestigationPlan } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import type { MessageKey } from "@/i18n/en";
import { Id } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pills";
import { formatDateTime, formatSeconds } from "@/lib/format";
import { readable, uniqueLines } from "@/lib/text";
import { stepModels, stepSeconds, stepText, type StepView } from "./steps";

type Row = Record<string, unknown>;

const asStrings = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => readable(item)) : []);
const asObjects = (value: unknown): Row[] =>
  Array.isArray(value) ? value.map((item) => (typeof item === "object" && item !== null ? (item as Row) : { id: String(item) })) : [];

function Label({ children }: { children: ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-wide text-muted">{children}</p>;
}

function List({ label, items }: { label: string; items: ReactNode[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <Label>{label}</Label>
      <ul className="mt-1.5 flex flex-col gap-1 text-sm text-ink">
        {items.map((item, index) => <li key={index} className="flex gap-2"><span className="text-muted">•</span><span className="min-w-0">{item}</span></li>)}
      </ul>
    </div>
  );
}

function Ids({ ids, max = 30 }: { ids: string[]; max?: number }) {
  return (
    <span className="flex flex-wrap gap-1">
      {ids.slice(0, max).map((id) => <span key={id} className="tabular rounded bg-neutral-soft px-1.5 py-0.5 text-xs text-muted">{id}</span>)}
      {ids.length > max && <span className="text-xs text-muted">+{ids.length - max}</span>}
    </span>
  );
}

/** Past records the historical review kept or set aside: the record and why, in words. */
function Records({ label, items, tone }: { label: string; items: Row[]; tone: "kept" | "dropped" }) {
  const { t } = useI18n();
  if (items.length === 0) return null;
  return (
    <div>
      <Label>{label} ({items.length})</Label>
      <ul className="mt-1.5 flex flex-col gap-1.5">
        {items.map((item, index) => (
          <li key={index} className={clsx("rounded-control px-3 py-2 text-sm", tone === "kept" ? "bg-success-soft/50" : "bg-neutral-soft")}>
            <span className="flex flex-wrap items-center gap-2">
              <Id className="text-ink">{readable(item.id ?? item.citation ?? "")}</Id>
              {item.came_back_after === true && <Pill tone="warning">{t("step.came_back")}</Pill>}
            </span>
            {typeof item.reason === "string" && <span className="mt-0.5 block text-muted">{item.reason}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

const FINDING_PARTS: [string, MessageKey][] = [
  ["similarities", "step.similarities"], ["differences", "step.differences"], ["remediation", "step.remediation"], ["outcome", "step.outcome"],
];

/** What a past case has in common with this problem, what differs, and how it ended. */
function Findings({ items }: { items: Row[] }) {
  const { t } = useI18n();
  if (items.length === 0) return null;
  return (
    <div>
      <Label>{t("step.findings")}</Label>
      <div className="mt-1.5 grid gap-2 lg:grid-cols-2">
        {items.map((finding, index) => (
          <div key={index} className="rounded-card border border-line bg-surface p-3">
            <Id className="text-ink">{readable(finding.citation ?? "")}</Id>
            <dl className="mt-1.5 flex flex-col gap-1 text-sm">
              {FINDING_PARTS.map(([key, label]) => {
                const value = finding[key];
                const text = Array.isArray(value) ? value.map(readable).join("; ") : value ? readable(value) : "";
                return text ? <div key={key}><dt className="inline font-medium text-ink">{t(label)}: </dt><dd className="inline text-muted">{text}</dd></div> : null;
              })}
            </dl>
          </div>
        ))}
      </div>
    </div>
  );
}

const READ_FLAGS = ["guidance", "notes", "instructions", "expert_request", "earlier_conclusions", "feedback"] as const;

/** What a step took into account beyond the problem itself, from the flags it saved in details.input. */
function TookIntoAccount({ input }: { input: Row | undefined }) {
  const { t } = useI18n();
  const read = READ_FLAGS.filter((flag) => input?.[flag] === true || (typeof input?.[flag] === "number" && (input[flag] as number) > 0));
  if (read.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted">{t("step.read")}:</span>
      {read.map((flag) => (
        <span key={flag} className={clsx("rounded-full px-2.5 py-0.5 text-xs font-semibold", flag === "expert_request" ? "bg-info-soft text-info" : "bg-brand-100 text-brand-800")}>
          {t(`step.read.${flag}`)}
        </span>
      ))}
    </div>
  );
}

const GIVEN: Record<string, MessageKey> = {
  "expert request": "step.given.expert request", notes: "step.given.notes", instructions: "step.given.instructions",
};

/** The texts the agents were given (notes, questions, the expert's request), each line once. */
function GivenTexts({ texts }: { texts: Row | undefined }) {
  const { t } = useI18n();
  const entries = Object.entries(texts ?? {}).filter((entry): entry is [string, string] => typeof entry[1] === "string" && entry[1].trim() !== "");
  if (entries.length === 0) return null;
  return (
    <div>
      <Label>{t("step.received")}</Label>
      <div className="mt-1.5 flex flex-col gap-2">
        {entries.map(([key, value]) => (
          <div key={key} className={clsx("rounded-control px-3 py-2", key === "expert request" ? "bg-info-soft/60" : "bg-neutral-soft")}>
            <p className="text-xs font-semibold text-ink">{GIVEN[key] ? t(GIVEN[key]!) : key}</p>
            <ul className="mt-1 list-disc pl-5 text-sm text-ink">{uniqueLines(value).map((line) => <li key={line}>{line}</li>)}</ul>
          </div>
        ))}
      </div>
    </div>
  );
}

const FOUND_LABEL: Record<string, MessageKey> = {
  logs: "step.found.logs", dependency_logs: "step.found.dependency_logs", changes: "step.found.changes", cmdb: "step.found.cmdb",
  problem_incidents: "step.found.problem_incidents", similar_incidents: "step.found.similar_incidents",
};

/** What one step did, in words; only what the saved step holds (nothing is inferred, nothing shown as raw data). */
export function StepDetails({ view, plan }: { view: StepView; plan: InvestigationPlan | null }) {
  const { t, language } = useI18n();
  const step = view.step;
  if (!step) {
    const text = stepText(view.name);
    return <p className="text-sm text-muted">{text ? t(text) : ""}</p>;
  }
  const details = step.details ?? {};
  const input = details.input as Row | undefined;
  const models = stepModels(step);
  const calls = (details.llm_calls as { input_tokens?: number; output_tokens?: number; latency_seconds?: number }[] | undefined) ?? [];
  const found = (details.found ?? null) as Record<string, string[]> | string[] | null;
  const runs = asObjects(details.tool_runs).map((run) => {
    const args = (run.arguments ?? {}) as Row;
    const target = readable(args.service ?? args.services ?? args.incident_id ?? "");
    const outcome = run.status === "ok" ? `${readable(run.result_count ?? 0)} ${t("step.found").toLowerCase()}` : `${readable(run.status)}${run.error ? `: ${readable(run.error)}` : ""}`;
    return `${target} · ${readable(run.tool ?? "")} · ${outcome}`;
  });
  const extra = asObjects(details.extra_searches).map((item) => `${readable(item.source)} · ${readable(item.service)}${item.reason ? ` — ${readable(item.reason)}` : ""}`);
  const refused = asObjects(details.refused_searches).map((item) => `${readable(item.source)} · ${readable(item.service)}${item.refused ? ` — ${readable(item.refused)}` : ""}`);
  const evidenceIds = asStrings(details.evidence_ids);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {models.length > 0 ? models.map((item) => (
          <span key={item.model} className="inline-flex items-center gap-1.5 rounded-full bg-[#EEE7FB] px-2.5 py-1 text-xs font-semibold text-[#4C2F96]">
            <Bot className="h-3.5 w-3.5" aria-hidden="true" />{t("step.agent")} · {item.provider} · {item.model}
          </span>
        )) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-neutral-soft px-2.5 py-1 text-xs font-medium text-muted">
            <Cpu className="h-3.5 w-3.5" aria-hidden="true" />{t("step.models_none")}
          </span>
        )}
        {stepSeconds(step) !== null && (
          <span className="inline-flex items-center gap-1 text-xs text-muted"><Clock3 className="h-3.5 w-3.5" aria-hidden="true" />{formatSeconds(stepSeconds(step), t)}</span>
        )}
        <span className="text-xs text-muted">{formatDateTime(step.started_at, language)}</span>
        {view.runs > 1 && <Pill tone="warning">{t("step.runs", { count: view.runs })}</Pill>}
      </div>

      <TookIntoAccount input={input} />

      <div>
        <Label>{t("step.summary")}</Label>
        <p className="mt-1 text-sm leading-relaxed text-ink">{step.summary}</p>
      </div>

      <GivenTexts texts={details.given_text as Row | undefined} />

      {calls.length > 0 && (
        <p className="text-xs text-muted">{t("step.llm_line", {
          count: calls.length,
          tokens_in: calls.reduce((sum, call) => sum + (call.input_tokens ?? 0), 0),
          tokens_out: calls.reduce((sum, call) => sum + (call.output_tokens ?? 0), 0),
          seconds: calls.reduce((sum, call) => sum + (call.latency_seconds ?? 0), 0).toFixed(1),
        })}</p>
      )}

      {view.name === "investigation_planner" && plan && (
        <div className="grid gap-3 sm:grid-cols-3">
          <div><Label>{t("step.service")}</Label><p className="mt-1 text-sm text-ink">{plan.service}</p></div>
          <div><Label>{t("step.window")}</Label><p className="mt-1 text-sm text-ink">{formatDateTime(plan.window_start, language)} – {formatDateTime(plan.window_end, language)}</p></div>
          <div><Label>{t("step.sources")}</Label><p className="mt-1 text-sm text-ink">{plan.sources.join(", ")}</p></div>
        </div>
      )}
      <List label={t("step.searched_for")} items={asStrings(details.search_queries)} />
      {typeof details.rationale === "string" && (
        <div><Label>{t("step.why")}</Label><p className="mt-1 text-sm leading-relaxed text-ink">{details.rationale}</p></div>
      )}
      <List label={t("step.extra_searches")} items={extra} />
      <List label={t("step.refused_searches")} items={refused} />
      <List label={t("step.services_searched")} items={asStrings(details.services)} />
      {found && !Array.isArray(found) && (
        <div className="grid gap-3 sm:grid-cols-2">
          {Object.entries(found).map(([key, ids]) => (
            <div key={key}>
              <Label>{FOUND_LABEL[key] ? t(FOUND_LABEL[key]!) : key} ({ids.length})</Label>
              <div className="mt-1">{ids.length ? <Ids ids={ids} /> : <span className="text-xs text-muted">{t("step.found_none")}</span>}</div>
            </div>
          ))}
        </div>
      )}
      {Array.isArray(found) && found.length > 0 && <div><Label>{t("step.found")} ({found.length})</Label><div className="mt-1"><Ids ids={asStrings(found)} /></div></div>}
      <List label={t("step.tool_runs")} items={runs} />
      {typeof details.moments === "number" && <p className="text-sm text-ink">{t("step.moments")}: <span className="tabular font-semibold">{details.moments}</span></p>}
      {typeof details.first_error === "string" && <p className="text-sm text-ink">{t("step.first_error")}: <Id>{details.first_error}</Id></p>}
      <Records label={t("step.kept")} items={asObjects(details.kept)} tone="kept" />
      <Records label={t("step.dropped")} items={asObjects(details.dropped)} tone="dropped" />
      <Findings items={asObjects(details.findings)} />
      {typeof details.attempt === "number" && <p className="text-sm text-muted">{t("step.attempt", { number: details.attempt })}</p>}
      <List label={t("step.problems")} items={asStrings(details.problems)} />
      <List label={t("step.warnings")} items={asStrings(details.warnings)} />
      {evidenceIds.length > 0 && <div><Label>{t("step.evidence_ids", { count: evidenceIds.length })}</Label><div className="mt-1"><Ids ids={evidenceIds} /></div></div>}
      {Object.keys(details).filter((key) => !["models", "input", "llm_calls"].includes(key)).length === 0 && <p className="text-sm text-muted">{t("step.no_detail")}</p>}
    </div>
  );
}
