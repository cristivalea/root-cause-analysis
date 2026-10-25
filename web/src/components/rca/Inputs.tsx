import type { ReactNode } from "react";
import type { RCARecord } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import type { MessageKey } from "@/i18n/en";
import { Id } from "@/components/ui/Card";
import { uniqueLines } from "@/lib/text";

function Heading({ children }: { children: ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-wide text-muted">{children}</p>;
}

function Bullets({ items }: { items: string[] }) {
  return <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-relaxed text-ink">{items.map((item, index) => <li key={index}>{item}</li>)}</ul>;
}

/** What an analysis received besides the problem: the services, the notes and questions, the expert's request,
 * the wider searches and earlier conclusions. Shown in the details of the "build context" step. */
export function Inputs({ record }: { record: RCARecord }) {
  const { t } = useI18n();
  const context = record.context;
  const guidance = record.guidance ?? context?.guidance ?? null;
  const searches = [
    guidance?.extra_services.length ? t("inputs.extra_services", { services: guidance.extra_services.join(", ") }) : null,
    guidance?.change_window_days ? t("inputs.change_days", { days: guidance.change_window_days }) : null,
    guidance?.log_hours_before ? t("inputs.log_hours", { hours: guidance.log_hours_before }) : null,
  ].filter(Boolean) as string[];
  const given: [MessageKey, ReactNode][] = [];
  if (context?.notes) given.push(["inputs.notes", <p className="text-sm text-ink">{context.notes}</p>]);
  if (context?.instructions) given.push(["inputs.instructions", <p className="text-sm text-ink">{context.instructions}</p>]);
  if (context?.expert_request) given.push(["inputs.expert_request", <Bullets items={uniqueLines(context.expert_request)} />]);
  if (searches.length) given.push(["inputs.searches", <Bullets items={searches} />]);
  if (context?.previous_conclusions.length) given.push(["inputs.previous", <Bullets items={context.previous_conclusions} />]);
  return (
    <div className="flex flex-col gap-5">
      {context && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div><Heading>{t("inputs.services")}</Heading><p className="mt-1 text-sm text-ink">{[...context.services, ...context.related_services].join(", ")}</p></div>
          <div><Heading>{t("inputs.reference")}</Heading><p className="mt-1"><Id>{context.reference_incident_id}</Id></p></div>
        </div>
      )}
      {given.length === 0 ? <p className="text-sm text-muted">{t("inputs.none")}</p> : given.map(([key, body]) => (
        <div key={key} className="rounded-card border border-line p-4"><Heading>{t(key)}</Heading><div className="mt-1.5">{body}</div></div>
      ))}
    </div>
  );
}
