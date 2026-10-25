import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { clsx } from "clsx";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, BookOpen, Eye, GitBranch, Scale, UserCheck } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import type { MessageKey } from "@/i18n/en";
import { LogoMark } from "@/components/layout/Logo";

export interface Step {
  title: MessageKey;
  text: MessageKey;
  icon: LucideIcon;
}

/** The greeting at the top of a home page, the link to how the application works, and room for the main ways in. */
export function Hero({ name, intro, children }: { name: string; intro: MessageKey; children?: ReactNode }) {
  const { t } = useI18n();
  return (
    <section className="relative overflow-hidden rounded-[20px] bg-brand-950 px-6 py-8 text-white sm:px-10 sm:py-10">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-sky-400/15 blur-3xl" />
        <LogoMark className="absolute -bottom-10 right-6 h-56 w-56 text-white/[0.05]" />
      </div>
      <div className="relative flex flex-col gap-8">
        <div className="max-w-xl animate-fade-up">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-[34px]">{t("home.greeting", { name })}</h1>
          <p className="mt-3 text-[15px] leading-relaxed text-white/75">{t(intro)}</p>
          <Link to="/how-it-works" className="group mt-4 inline-flex items-center gap-2 text-sm font-semibold text-sky-200 hover:text-white">
            <BookOpen className="h-4 w-4" aria-hidden="true" />{t("guide.link")}
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
          </Link>
        </div>
        {children && <div className="relative grid gap-3 md:grid-cols-2 xl:max-w-4xl">{children}</div>}
      </div>
    </section>
  );
}

/** The steps of the process as a connected row (a column on small screens), numbered 01, 02, … */
export function ProcessSteps({ title, subtitle, steps }: { title: MessageKey; subtitle?: MessageKey; steps: Step[] }) {
  const { t } = useI18n();
  return (
    <section aria-labelledby="process-title">
      <h2 id="process-title" className="text-xl font-semibold tracking-tight text-ink">{t(title)}</h2>
      {subtitle && <p className="mt-1 text-sm text-muted">{t(subtitle)}</p>}
      <ol className={clsx("mt-6 grid gap-4", steps.length === 5 ? "md:grid-cols-5" : "md:grid-cols-4")}>
        {steps.map(({ title: stepTitle, text, icon: Icon }, index) => (
          <li key={stepTitle} className="relative animate-fade-up" style={{ animationDelay: `${index * 90}ms` }}>
            {index < steps.length - 1 && (
              <span aria-hidden="true" className="absolute left-[calc(50%+28px)] right-[calc(-50%+28px)] top-6 hidden h-0.5 bg-gradient-to-r from-brand-600/50 to-brand-600/10 md:block" />
            )}
            <div className="flex gap-4 md:flex-col md:items-center md:text-center">
              <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700 ring-4 ring-bg">
                <Icon className="h-5 w-5" aria-hidden="true" />
                <span className="tabular absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-600 px-1 text-[10px] font-bold text-white">
                  {String(index + 1).padStart(2, "0")}
                </span>
              </div>
              <div>
                <h3 className="font-semibold text-ink">{t(stepTitle)}</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted">{t(text)}</p>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

const CLAIMS: { title: MessageKey; text: MessageKey; icon: LucideIcon; tone: string }[] = [
  { title: "home.claim1.title", text: "home.claim1.text", icon: Eye, tone: "bg-[#FDE2E1] text-[#B5352F]" },
  { title: "home.claim2.title", text: "home.claim2.text", icon: Scale, tone: "bg-[#EEE7FB] text-[#5B3DB0]" },
  { title: "home.claim3.title", text: "home.claim3.text", icon: GitBranch, tone: "bg-[#E0ECFB] text-[#2A62B3]" },
  { title: "home.claim4.title", text: "home.claim4.text", icon: UserCheck, tone: "bg-[#DDF3E4] text-[#1F7A45]" },
];

/** "Treat explanations as claims to test": the principles every analysis follows, as four small cards. */
export function Claims() {
  const { t } = useI18n();
  return (
    <section aria-labelledby="claims-title">
      <h2 id="claims-title" className="text-xl font-semibold tracking-tight text-ink">{t("home.claims_title")}</h2>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {CLAIMS.map(({ title, text, icon: Icon, tone }, index) => (
          <div key={title} className="rounded-card border border-line bg-surface p-5 shadow-card transition-transform duration-150 hover:-translate-y-0.5 animate-fade-up"
               style={{ animationDelay: `${index * 80}ms` }}>
            <span className={clsx("inline-flex h-10 w-10 items-center justify-center rounded-control", tone)}>
              <Icon className="h-5 w-5" aria-hidden="true" />
            </span>
            <h3 className="mt-4 font-semibold text-ink">{t(title)}</h3>
            <p className="mt-1 text-sm leading-relaxed text-muted">{t(text)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
