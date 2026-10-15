import { clsx } from "clsx";
import { CircleHelp, FileSearch } from "lucide-react";
import type { CauseFactor, FishboneCategory } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { NODE } from "./FiveWhysDiagram";

/** The six categories of the model (models.FishboneCategory), each with its own pastel colour. */
const CATEGORY: Record<FishboneCategory, { box: string; line: string }> = {
  "Change / Release": { box: "border-[#3B7DD8] bg-[#E0ECFB] text-[#173E73]", line: "#3B7DD8" },
  Configuration: { box: "border-[#7C5CCB] bg-[#EEE7FB] text-[#4C2F96]", line: "#7C5CCB" },
  Capacity: { box: "border-[#E8891C] bg-[#FFE8CC] text-[#7A4300]", line: "#E8891C" },
  Dependencies: { box: "border-[#0F7F6F] bg-[#DDF2EE] text-[#0E4F47]", line: "#0F7F6F" },
  Monitoring: { box: "border-[#D9488B] bg-[#FCE4F0] text-[#7D1F4C]", line: "#D9488B" },
  Process: { box: "border-[#5A6763] bg-[#EEF1F0] text-[#2B3532]", line: "#5A6763" },
};
const ORDER = Object.keys(CATEGORY) as FishboneCategory[];

export interface FishFactor extends CauseFactor {
  evidenceLabels: { id: string; label: string }[];
}

function Bone({ category, factors, top, delay }: { category: FishboneCategory; factors: FishFactor[]; top: boolean; delay: number }) {
  const { t } = useI18n();
  const colour = CATEGORY[category];
  const card = (
    <div className={clsx("w-[220px] rounded-[12px] border-2 p-3 shadow-card", colour.box)}>
      <p className="text-[11px] font-bold uppercase tracking-wide">{t(`fishbone.${category}`)}</p>
      <ul className="mt-2 flex flex-col gap-1.5">
        {factors.map((factor, index) => (
          <li key={index} className={clsx("rounded-md bg-white/70 px-2 py-1.5 text-xs leading-snug text-ink", factor.evidence.length === 0 && "border border-dashed border-current")}>
            {factor.factor}
            <span className="mt-1 flex flex-wrap gap-1">
              {factor.evidence.length === 0 ? (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-muted"><CircleHelp className="h-3 w-3" aria-hidden="true" />{t("diagram.to_check")}</span>
              ) : factor.evidenceLabels.map((item) => (
                <span key={item.id} className={clsx("inline-flex items-center gap-1 rounded-full border px-1.5 py-px text-[10px] font-semibold", NODE.evidence)}>
                  <FileSearch className="h-2.5 w-2.5" aria-hidden="true" />{item.label}
                </span>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
  const connector = (
    <svg width="220" height="34" className="block" aria-hidden="true">
      <line x1="110" y1={top ? 0 : 34} x2="160" y2={top ? 34 : 0} stroke={colour.line} strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
  return (
    <div className="flex flex-col animate-fade-up" style={{ animationDelay: `${delay}ms` }}>
      {top ? <>{card}{connector}</> : <>{connector}{card}</>}
    </div>
  );
}

/** A fishbone (Ishikawa) diagram: the problem at the head, the categories as bones above and below the
 * spine, each listing its factors and the evidence behind them. Only categories with factors are drawn. */
export function FishboneDiagram({ problem, factors }: { problem: string; factors: FishFactor[] }) {
  const used = ORDER.filter((category) => factors.some((factor) => factor.category === category));
  const top = used.filter((_, index) => index % 2 === 0);
  const bottom = used.filter((_, index) => index % 2 === 1);
  const of = (category: FishboneCategory) => factors.filter((factor) => factor.category === category);

  return (
    <div className="flex items-center gap-0 py-2">
      <div className="flex flex-col">
        <div className="flex items-end gap-5 pl-4">
          {top.map((category, index) => <Bone key={category} category={category} factors={of(category)} top delay={index * 120} />)}
        </div>
        <div className="relative h-1.5 rounded-full bg-[#9AA8A4]" style={{ minWidth: Math.max(top.length, bottom.length) * 240 + 24 }} aria-hidden="true">
          <span className="absolute -right-1 top-1/2 h-0 w-0 -translate-y-1/2 border-y-[9px] border-l-[14px] border-y-transparent border-l-[#9AA8A4]" />
        </div>
        <div className="flex items-start gap-5 pl-4">
          {bottom.map((category, index) => <Bone key={category} category={category} factors={of(category)} top={false} delay={index * 120 + 60} />)}
        </div>
      </div>
      <div className={clsx("ml-4 w-[220px] shrink-0 rounded-[18px] border-2 px-4 py-4 text-center text-sm font-semibold leading-snug shadow-card animate-fade-up", NODE.problem)}>
        {problem}
      </div>
    </div>
  );
}
