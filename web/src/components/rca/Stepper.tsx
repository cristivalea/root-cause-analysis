import { useEffect, useState } from "react";
import { clsx } from "clsx";
import { AlertTriangle, Bot, Check, Loader2 } from "lucide-react";
import type { InvestigationPlan, InvestigationStep } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { formatSeconds } from "@/lib/format";
import { StepDetails } from "./StepDetails";
import { stepModels, stepSeconds, stepTitle, stepViews, type StepState } from "./steps";

const DOT: Record<StepState, string> = {
  done: "bg-brand-600 text-white border-brand-600",
  running: "bg-info-soft text-info border-info animate-pulse",
  queued: "bg-surface text-muted border-line",
  failed: "bg-danger text-white border-danger",
};

function StateIcon({ state, index }: { state: StepState; index: number }) {
  if (state === "done") return <Check className="h-4 w-4" aria-hidden="true" />;
  if (state === "running") return <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />;
  if (state === "failed") return <AlertTriangle className="h-4 w-4" aria-hidden="true" />;
  return <span className="tabular text-xs font-semibold">{index + 1}</span>;
}

/** The investigation as a horizontal stepper (Ant Design "title placement" pattern): one dot per step,
 * its title under it, its state, time and model; the chosen step opens its details below. On a narrow
 * screen the row scrolls inside its own box. */
export function Stepper({ trace, plan, running, failed, current }: {
  trace: InvestigationStep[];
  plan: InvestigationPlan | null;
  running: boolean;
  failed: boolean;
  current: string | null;
}) {
  const { t } = useI18n();
  const views = stepViews(trace, { running, failed, current });
  const active = views.find((view) => view.state === "running" || view.state === "failed")?.name;
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (running && active) setSelected(active);
  }, [running, active]);

  const chosen = views.find((view) => view.name === selected);

  return (
    <div>
      <div className="-mx-1 overflow-x-auto px-1 pb-2">
        <ol className="grid min-w-[880px] gap-0" style={{ gridTemplateColumns: `repeat(${views.length}, minmax(0, 1fr))` }}>
          {views.map((view, index) => {
            const title = stepTitle(view.name);
            const models = stepModels(view.step);
            const seconds = stepSeconds(view.step);
            const isSelected = selected === view.name;
            return (
              <li key={view.name} className="relative">
                {index < views.length - 1 && (
                  <span aria-hidden="true" className={clsx("absolute left-[calc(50%+20px)] right-[calc(-50%+20px)] top-[19px] h-0.5 rounded-full",
                    view.state === "done" ? "bg-brand-600" : "bg-line")} />
                )}
                <button
                  type="button"
                  onClick={() => setSelected(isSelected ? null : view.name)}
                  aria-expanded={isSelected}
                  aria-label={`${title ? t(title) : view.name}: ${t(`step.state.${view.state}`)}`}
                  className={clsx("group flex w-full flex-col items-center rounded-card px-1.5 pb-2 pt-0.5 text-center transition-colors",
                    isSelected ? "bg-brand-50" : "hover:bg-brand-50/60")}
                >
                  <span className={clsx("relative z-10 flex h-10 w-10 items-center justify-center rounded-full border-2 ring-4 ring-surface transition-transform group-hover:scale-105", DOT[view.state])}>
                    <StateIcon state={view.state} index={index} />
                  </span>
                  <span className={clsx("mt-2 text-[13px] font-semibold leading-tight", view.state === "queued" ? "text-muted" : "text-ink")}>
                    {title ? t(title) : view.name}
                  </span>
                  <span className="mt-0.5 text-[11px] text-muted">
                    {view.state === "done" && seconds !== null ? formatSeconds(seconds, t) : t(`step.state.${view.state}`)}
                  </span>
                  {models.length > 0 && (
                    <span className="mt-1 inline-flex max-w-full items-center gap-1 truncate rounded-full bg-[#EEE7FB] px-2 py-0.5 text-[10px] font-semibold text-[#4C2F96]" title={models.map((item) => `${item.provider} · ${item.model}`).join(", ")}>
                      <Bot className="h-3 w-3 shrink-0" aria-hidden="true" />
                      <span className="truncate">{models[0]!.model.split("/").pop()}</span>
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ol>
      </div>
      {chosen ? (
        <div className="mt-3 rounded-card border border-brand-600/20 bg-brand-50/40 p-4 animate-fade-in sm:p-5">
          <p className="mb-3 font-semibold text-ink">{stepTitle(chosen.name) ? t(stepTitle(chosen.name)!) : chosen.name}</p>
          <StepDetails view={chosen} plan={plan} />
        </div>
      ) : (
        <p className="mt-2 text-center text-xs text-muted">{t("inv.steps_hint")}</p>
      )}
    </div>
  );
}
