import type { InvestigationStep } from "@/api/types";
import type { MessageKey } from "@/i18n/en";

/** The nodes of the graph in the order they run (rca/pipeline.py), as rca/ui/components/investigation_timeline.py. */
export const STEPS = [
  "build_context", "investigation_planner", "gather_evidence", "build_timeline",
  "historical_review", "rca_reasoning_agent", "guardrail", "confidence",
] as const;

/** Names of steps in RCAs saved before the redesign, shown as their new step. */
export const ALIASES: Record<string, string> = { tools: "gather_evidence", historical_rca_agent: "historical_review" };

const KNOWN = new Set<string>([...STEPS, "similar_incidents"]);
export type StepState = "done" | "running" | "queued" | "failed";

export interface StepView {
  name: string; // the name shown (an alias already resolved)
  state: StepState;
  step: InvestigationStep | undefined; // the last run of this step
  runs: number;
}

export const canonical = (name: string) => ALIASES[name] ?? name;

export function stepTitle(name: string): MessageKey | null {
  return KNOWN.has(name) ? (`step.${name}.title` as MessageKey) : null;
}

export function stepText(name: string): MessageKey | null {
  return KNOWN.has(name) ? (`step.${name}.text` as MessageKey) : null;
}

/** The steps to show, in order, with the state of each: the nodes of the graph, plus any step the trace
 * holds that the list does not know (an older RCA), placed where it ran. A step that ran several times
 * (a refused draft asked again) shows its last run. current is the node LangGraph reports as running. */
export function stepViews(trace: InvestigationStep[], opts: { running: boolean; failed: boolean; current: string | null }): StepView[] {
  const names = trace.map((item) => canonical(item.name));
  const order: string[] = [...STEPS];
  names.forEach((name, index) => {
    if (order.includes(name)) return;
    const next = names.slice(index + 1).find((later) => order.includes(later));
    order.splice(next ? order.indexOf(next) : order.length, 0, name);
  });

  const last = new Map<string, InvestigationStep>();
  const runs = new Map<string, number>();
  trace.forEach((item) => {
    const name = canonical(item.name);
    last.set(name, item);
    runs.set(name, (runs.get(name) ?? 0) + 1);
  });

  const current = opts.current ? canonical(opts.current) : order.find((name) => !last.has(name)) ?? null;
  const views = order.map((name) => {
    let state: StepState = "queued";
    if (opts.running && name === current) state = "running";
    else if (last.has(name)) state = "done";
    else if (opts.failed && name === current) state = "failed";
    return { name, state, step: last.get(name), runs: runs.get(name) ?? 0 };
  });
  // a finished run shows what it did: a step it never ran (an older version of the graph) is not "waiting"
  return opts.running ? views : views.filter((view) => view.state !== "queued");
}

const PROVIDERS: Record<string, string> = { groq: "Groq", gemini: "Gemini", openrouter: "OpenRouter" };

/** The models that answered an agent step, as the step saved them ("groq:openai/gpt-oss-120b"). Nothing is
 * inferred: a step without details.models shows no model. */
export function stepModels(step: InvestigationStep | undefined): { provider: string; model: string }[] {
  const models = (step?.details?.models as string[] | undefined) ?? [];
  const seen = new Set<string>();
  return models.flatMap((entry) => {
    const [provider = "", ...rest] = entry.split(":");
    const model = rest.join(":");
    const key = `${provider}:${model}`;
    if (seen.has(key)) return [];
    seen.add(key);
    return [{ provider: PROVIDERS[provider] ?? provider, model }];
  });
}

export function stepSeconds(step: InvestigationStep | undefined): number | null {
  if (!step?.finished_at) return null;
  return (new Date(step.finished_at).getTime() - new Date(step.started_at).getTime()) / 1000;
}
