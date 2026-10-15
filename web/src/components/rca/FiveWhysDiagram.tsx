import { useState, type ReactNode } from "react";
import { clsx } from "clsx";
import { CircleHelp, FileSearch } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

export interface WhyNode {
  /** The answer to "why?" at this step. */
  text: string;
  /** The evidence the step rests on, as people read it (e.g. "EV-004 · CHG-2026-00871"). Empty: an open question. */
  evidence: { id: string; label: string }[];
}

/** The pastel colours of the mymap.ai example, by the role of a node in the chain. */
export const NODE = {
  problem: "border-[#D9534F] bg-[#FDE2E1] text-[#7A1F1C]",
  why: "border-[#E8891C] bg-[#FFE8CC] text-[#7A4300]",
  answer: "border-[#3B7DD8] bg-[#E0ECFB] text-[#173E73]",
  root: "border-[#2E9B5B] bg-[#DDF3E4] text-[#14532D]",
  evidence: "border-[#7C5CCB]/40 bg-[#EEE7FB] text-[#4C2F96]",
} as const;

function Connector({ delay }: { delay: number }) {
  return (
    <div className="flex h-5 justify-center animate-fade-in" style={{ animationDelay: `${delay}ms` }} aria-hidden="true">
      <div className="w-0.5 rounded-full bg-[#B9C3C0]" />
    </div>
  );
}

function Why({ delay, label }: { delay: number; label: string }) {
  return (
    <div className="flex justify-center animate-fade-up" style={{ animationDelay: `${delay}ms` }} aria-hidden="true">
      <div className={clsx("flex h-10 w-10 rotate-45 items-center justify-center rounded-[6px] border-2 shadow-card", NODE.why)}>
        <span className="-rotate-45 text-[11px] font-bold">{label}</span>
      </div>
    </div>
  );
}

function Box({ tone, children, delay, dashed = false, pill = false, active, onHover }: {
  tone: keyof typeof NODE;
  children: ReactNode;
  delay: number;
  dashed?: boolean;
  pill?: boolean;
  active?: boolean;
  onHover?: (hovered: boolean) => void;
}) {
  return (
    <div
      className={clsx(
        "mx-auto w-[400px] max-w-full border-2 px-5 py-3 text-center text-sm font-medium leading-snug shadow-card",
        "transition-[transform,box-shadow] duration-150 animate-fade-up",
        pill ? "rounded-full" : "rounded-[10px]",
        dashed && "border-dashed",
        active && "-translate-y-0.5 shadow-pop",
        NODE[tone],
      )}
      style={{ animationDelay: `${delay}ms` }}
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
    >
      {children}
    </div>
  );
}

/** A 5 Whys chain: the symptom (red), each "why?" (orange diamond) and its answer (blue), down to the
 * root cause (green). A step without evidence is dashed and marked "to check": the chain stops where the
 * evidence stops (rca/diagram.py), nothing is added to reach five. Nodes appear one after the other. */
export function FiveWhysDiagram({ problem, steps, root, rootLabel }: {
  problem: string;
  steps: WhyNode[];
  root?: string;
  rootLabel?: string;
}) {
  const { t } = useI18n();
  const [hovered, setHovered] = useState<number | null>(null);
  let delay = 0;
  const next = () => (delay += 110);

  return (
    <div className="w-[440px] py-1">
      <Box tone="problem" pill delay={0}>{problem}</Box>
      {steps.map((step, index) => {
        const open = step.evidence.length === 0;
        return (
          <div key={index}>
            <Connector delay={next()} />
            <Why delay={next()} label={t("diagram.why")} />
            <Connector delay={delay} />
            <Box tone="answer" delay={next()} dashed={open} active={hovered === index} onHover={(on) => setHovered(on ? index : null)}>
              <span className="block">{step.text}</span>
              <span className="mt-2 flex flex-wrap justify-center gap-1">
                {open ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-current px-2 py-0.5 text-[11px] font-semibold">
                    <CircleHelp className="h-3 w-3" aria-hidden="true" />
                    {t("diagram.to_check")}
                  </span>
                ) : (
                  step.evidence.map((item) => (
                    <span key={item.id} className={clsx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold", NODE.evidence)}>
                      <FileSearch className="h-3 w-3" aria-hidden="true" />
                      {item.label}
                    </span>
                  ))
                )}
              </span>
            </Box>
          </div>
        );
      })}
      {root && (
        <>
          <Connector delay={next()} />
          <Box tone="root" pill delay={next()}>
            {rootLabel && <span className="block text-[11px] font-bold uppercase tracking-wide opacity-80">{rootLabel}</span>}
            {root}
          </Box>
        </>
      )}
    </div>
  );
}
