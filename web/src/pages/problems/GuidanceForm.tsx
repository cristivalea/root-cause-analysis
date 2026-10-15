import { clsx } from "clsx";
import { Check } from "lucide-react";
import { useServices } from "@/api/queries";
import { useI18n } from "@/i18n/I18nProvider";
import { TextArea, TextInput } from "@/components/ui/Field";
import { Skeleton } from "@/components/ui/States";
import { CHANGE_DAYS, LOG_HOURS, draftErrors, type GuidanceDraft } from "./guidance";

/** The optional guidance of an investigation: notes, questions, more services, wider windows. */
export function GuidanceForm({ draft, onChange, disabled, exclude = [], searchesOnly = false }: {
  draft: GuidanceDraft;
  onChange: (draft: GuidanceDraft) => void;
  disabled?: boolean;
  exclude?: string[];
  /** Only the wider searches (services, windows): the expert's request carries its own text. */
  searchesOnly?: boolean;
}) {
  const { t } = useI18n();
  const services = useServices();
  const errors = draftErrors(draft);
  const set = (change: Partial<GuidanceDraft>) => onChange({ ...draft, ...change });
  const options = (services.data ?? []).filter((service) => !exclude.includes(service));
  const toggle = (service: string) =>
    set({ services: draft.services.includes(service) ? draft.services.filter((item) => item !== service) : [...draft.services, service] });

  return (
    <fieldset disabled={disabled} className="flex flex-col gap-4">
      {!searchesOnly && (
        <>
          <p className="text-sm text-muted">{t("guidance.hint")}</p>
          <TextArea label={t("guidance.notes")} hint={t("guidance.notes_help")} rows={2} value={draft.notes}
                    onChange={(event) => set({ notes: event.target.value })} maxLength={4000} />
          <TextArea label={t("guidance.instructions")} hint={t("guidance.instructions_help")} rows={2} value={draft.instructions}
                    onChange={(event) => set({ instructions: event.target.value })} maxLength={4000} />
        </>
      )}
      <div>
        <p className="text-sm font-medium text-ink">{t("guidance.services")}</p>
        <p className="text-xs text-muted">{t("guidance.services_help")}</p>
        <div className="mt-2 flex max-h-40 flex-wrap gap-1.5 overflow-y-auto" role="group" aria-label={t("guidance.services")}>
          {services.isPending && <Skeleton className="h-7 w-full" />}
          {options.map((service) => {
            const chosen = draft.services.includes(service);
            return (
              <button key={service} type="button" aria-pressed={chosen} onClick={() => toggle(service)}
                      className={clsx("inline-flex h-7 items-center gap-1 rounded-full border px-2.5 text-xs font-medium transition-colors",
                        chosen ? "border-brand-600 bg-brand-100 text-brand-800" : "border-line bg-surface text-muted hover:border-brand-600/40 hover:text-ink")}>
                {chosen && <Check className="h-3 w-3" aria-hidden="true" />}
                {service}
              </button>
            );
          })}
        </div>
      </div>
      <div className="grid gap-3">
        <TextInput label={t("guidance.change_days")} hint={t("guidance.change_days_help")} type="number" inputMode="numeric"
                   min={CHANGE_DAYS.min} max={CHANGE_DAYS.max} value={draft.changeDays}
                   onChange={(event) => set({ changeDays: event.target.value })}
                   error={errors.changeDays ? t("guidance.range", CHANGE_DAYS) : null} />
        <TextInput label={t("guidance.log_hours")} hint={t("guidance.log_hours_help")} type="number" inputMode="numeric"
                   min={LOG_HOURS.min} max={LOG_HOURS.max} value={draft.logHours}
                   onChange={(event) => set({ logHours: event.target.value })}
                   error={errors.logHours ? t("guidance.range", LOG_HOURS) : null} />
      </div>
    </fieldset>
  );
}
