import * as Popover from "@radix-ui/react-popover";
import { clsx } from "clsx";
import { FileSearch, Info } from "lucide-react";
import type { Evidence, EvidenceType } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Id } from "@/components/ui/Card";
import { evidenceSummary } from "@/lib/evidence";
import { formatDateTime } from "@/lib/format";

export const TYPE_TONE: Record<EvidenceType, string> = {
  INCIDENT: "bg-[#FDE2E1] text-[#7A1F1C]", LOG: "bg-[#E0ECFB] text-[#173E73]", CHANGE: "bg-[#FFE8CC] text-[#7A4300]",
  CMDB: "bg-[#DDF2EE] text-[#0E4F47]", HISTORICAL_RCA: "bg-[#EEE7FB] text-[#4C2F96]", HISTORICAL_INCIDENT: "bg-[#FCE4F0] text-[#7D1F4C]",
};

/** A piece of evidence as people read it, "Change: Deploy auth-service Helm chart 5.2.0", with an info button
 * that opens the details: the whole text, the codes, the source and the time. A click, not a hover, so it
 * works on a touch screen and with the keyboard. */
export function EvidenceChip({ item }: { item: Evidence }) {
  const { t, language } = useI18n();
  const type = t(`evidence.type.${item.type}`);
  const summary = evidenceSummary(item);
  return (
    <span className={clsx("inline-flex max-w-full items-center gap-1 rounded-full py-0.5 pl-2 pr-0.5 text-[11px] font-semibold", TYPE_TONE[item.type])}>
      <FileSearch className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span className="truncate">{type}: <span className="font-medium">{summary}</span></span>
      <Popover.Root>
        <Popover.Trigger
          aria-label={t("evidence.details", { label: `${type}: ${summary}` })}
          className="ml-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full hover:bg-black/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
        >
          <Info className="h-3.5 w-3.5" aria-hidden="true" />
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            sideOffset={6}
            collisionPadding={16}
            className="z-40 w-[min(380px,calc(100vw-2rem))] rounded-card border border-line bg-surface p-4 text-sm shadow-pop animate-scale-in"
          >
            <span className={clsx("inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold", TYPE_TONE[item.type])}>{type}</span>
            <p className="mt-2 font-semibold leading-snug text-ink">{summary}</p>
            <p className="mt-2 max-h-48 overflow-y-auto leading-relaxed text-muted">{item.description}</p>
            <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 border-t border-line pt-3 text-xs">
              <dt className="text-muted">{t("evidence.code")}</dt><dd><Id>{item.citation}</Id></dd>
              {item.source !== item.citation && <><dt className="text-muted">{t("evidence.source")}</dt><dd className="break-words text-ink">{item.source}</dd></>}
              {item.timestamp && <><dt className="text-muted">{t("evidence.when")}</dt><dd className="text-ink">{formatDateTime(item.timestamp, language)}</dd></>}
              <dt className="text-muted">{t("evidence.number")}</dt><dd><Id>{item.evidence_id}</Id></dd>
            </dl>
            <Popover.Arrow className="fill-surface" />
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </span>
  );
}
