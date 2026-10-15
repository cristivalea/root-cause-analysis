import type { ReactNode } from "react";
import { clsx } from "clsx";
import { AlertTriangle, CheckCircle2, FlaskConical, HelpCircle, Info, Scale } from "lucide-react";
import { useKpis } from "@/api/queries";
import type { KpiBenchmark, KpiReport } from "@/api/types";
import { useI18n, type Translate } from "@/i18n/I18nProvider";
import type { MessageKey } from "@/i18n/en";
import { Card, PageHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { PillTabs } from "@/components/ui/PillTabs";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { BarList, Columns, SERIES, StackedBar } from "@/components/charts/Charts";
import { formatDate } from "@/lib/format";
import { useUrlState } from "@/lib/useUrlState";

type Period = "7" | "30" | "90" | "all";
const PERIODS: Period[] = ["7", "30", "90", "all"];
const DEFAULTS = { period: "all" };
const FEW = 10; // below this many cases a percentage is a first signal, and the card says so

function startOf(period: Period): string | null {
  if (period === "all") return null;
  const day = new Date();
  day.setDate(day.getDate() - Number(period) + 1);
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
}

// as computed, at most two decimals (the 63.64 % of docs/KPIS.md stays 63.64 %)
const pct = (value: number | null) => (value === null ? "—" : `${Math.round(value * 100) / 100}%`);

function duration(hours: number | null, t: Translate) {
  if (hours === null) return t("kpis.now.median_none");
  return hours < 1 ? t("kpis.minutes", { count: Math.max(1, Math.round(hours * 60)) }) : t("kpis.hours", { count: hours.toFixed(1) });
}

function StatTile({ label, value, tone }: { label: string; value: ReactNode; tone?: "warning" | "danger" }) {
  return (
    <div className="rounded-card border border-line bg-surface px-4 py-3.5 shadow-card">
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className={clsx("mt-1 text-2xl font-semibold tracking-tight", tone === "warning" ? "text-warning" : tone === "danger" ? "text-danger" : "text-ink")}>{value}</p>
    </div>
  );
}

/** The base of a percentage, and a warning when it is too small to mean much. */
function Basis({ text, count }: { text: string; count: number }) {
  const { t } = useI18n();
  return (
    <p className="mt-1 text-xs text-muted">
      {text}
      {count > 0 && count < FEW && <span className="ml-1 inline-flex items-center gap-1 text-warning"><AlertTriangle className="h-3 w-3" aria-hidden="true" />{t("kpis.few")}</span>}
    </p>
  );
}

function Hero({ value, unit }: { value: string; unit?: string }) {
  return (
    <p className="flex flex-wrap items-baseline gap-x-2">
      <span className="text-5xl font-semibold tracking-tight text-ink">{value}</span>
      {unit && <span className="text-sm text-muted">{unit}</span>}
    </p>
  );
}

/** One KPI: the question it answers, its number, its chart, and how it is calculated and read. */
function KpiCard({ tag, title, question, how, read, children, icon }: {
  tag: MessageKey; title: MessageKey; question: MessageKey; how: MessageKey; read: MessageKey; children: ReactNode; icon: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <Card className="flex flex-col p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-brand-100 text-brand-700">{icon}</span>
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-wide text-brand-700">{t(tag)}</p>
          <h2 className="text-lg font-semibold text-ink">{t(title)}</h2>
          <p className="mt-0.5 text-sm text-muted">{t(question)}</p>
        </div>
      </div>
      <div className="mt-5 flex-1">{children}</div>
      <div className="mt-5 flex flex-col gap-1 border-t border-line pt-3">
        <Disclosure label={t("kpis.how")} icon={<HelpCircle className="h-4 w-4" aria-hidden="true" />}>
          <p className="text-sm leading-relaxed text-ink">{t(how)}</p>
        </Disclosure>
        <Disclosure label={t("kpis.read")} icon={<Info className="h-4 w-4" aria-hidden="true" />}>
          <p className="text-sm leading-relaxed text-ink">{t(read)}</p>
        </Disclosure>
      </div>
    </Card>
  );
}

/** The exam on the 13 prepared cases: its result, or why there is none. Never a made-up number. */
function BenchmarkPanel({ bench, children }: { bench: KpiBenchmark; children?: ReactNode }) {
  const { t, language } = useI18n();
  return (
    <div className="mt-5 rounded-card border border-dashed border-line bg-bg/60 p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-ink"><FlaskConical className="h-4 w-4 text-brand-600" aria-hidden="true" />{t("kpis.benchmark")}</p>
      {bench.status === "measured" ? (
        <>
          <div className="mt-2">{children}</div>
          <p className="mt-2 text-xs text-muted">{t("kpis.bench.measured", {
            date: formatDate(bench.timestamp, language), evaluated: bench.evaluated ?? "—", selected: bench.selected ?? "—", model: bench.agent_model ?? "—",
          })}</p>
          {bench.excluded.length > 0 && <p className="mt-0.5 text-xs text-muted">{t("kpis.bench.excluded", { ids: bench.excluded.join(", ") })}</p>}
        </>
      ) : (
        <p className="mt-1.5 break-words text-sm text-muted">
          {bench.status === "outdated" ? t("kpis.bench.outdated", { date: formatDate(bench.timestamp, language) }) : t("kpis.bench.not_measured")}
        </p>
      )}
    </div>
  );
}

function Kpi1({ data }: { data: KpiReport["kpi1_interactions"] }) {
  const { t } = useI18n();
  const average = data.average_interactions;
  return (
    <>
      <Hero value={pct(data.reduction_percent)} unit={t("kpi1.unit")} />
      <Basis text={data.finished ? t("kpis.cases", { count: data.finished }) : t("kpis.none")} count={data.finished} />
      <p className="mt-1 text-xs text-muted">{t("kpis.design")}: <span className="font-semibold text-ink">{pct(data.design_reduction_percent)}</span></p>
      {average !== null && (
        <div className="mt-5">
          <BarList caption={t("kpi1.title")} max={data.manual_interactions} bars={[
            { label: t("kpi1.bar.manual"), value: data.manual_interactions, display: String(data.manual_interactions), colour: SERIES.rest },
            { label: t("kpi1.bar.app"), value: average, display: average.toFixed(1) },
            { label: t("kpi1.bar.design"), value: data.design_interactions, display: String(data.design_interactions), colour: SERIES.rest },
          ]} />
          <p className="mt-3 text-xs text-muted">{t("kpi1.split", { happy: data.happy_path, more: data.with_more_steps })}</p>
        </div>
      )}
    </>
  );
}

function Kpi2({ data }: { data: KpiReport["kpi2_autonomy"] }) {
  const { t } = useI18n();
  return (
    <>
      <Hero value={pct(data.rate_percent)} unit={t("kpi2.unit")} />
      <Basis text={data.runs ? t("kpis.runs", { count: data.runs }) : t("kpis.none")} count={data.runs} />
      <p className="mt-1 text-xs text-muted">{t("kpis.design")}: <span className="font-semibold text-ink">{pct(data.design_percent)}</span> — {t("kpi2.design_text", { automated: data.design_automated, stages: data.design_stages })}</p>
      {data.runs > 0 && (
        <div className="mt-5">
          <StackedBar caption={t("kpi2.title")} segments={[
            { label: t("kpi2.seg.auto"), value: data.autonomous, colour: SERIES.blue },
            { label: t("kpi2.seg.refused"), value: data.refused_by_checks, colour: SERIES.orange },
            { label: t("kpi2.seg.failed"), value: data.failed, colour: SERIES.aqua },
          ]} />
        </div>
      )}
    </>
  );
}

function Pair({ items }: { items: { label: string; value: string }[] }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {items.map((item) => (
        <div key={item.label}>
          <p className="text-4xl font-semibold tracking-tight text-ink">{item.value}</p>
          <p className="mt-0.5 text-xs text-muted">{item.label}</p>
        </div>
      ))}
    </div>
  );
}

function Kpi3({ data, bench }: { data: KpiReport["kpi3_accuracy"]; bench: KpiBenchmark }) {
  const { t } = useI18n();
  return (
    <>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{t("kpis.live")}</p>
      <Pair items={[{ label: t("kpi3.top1"), value: pct(data.top1_percent) }, { label: t("kpi3.topk"), value: pct(data.topk_percent) }]} />
      <Basis text={data.decided ? t("kpis.cases", { count: data.decided }) : t("kpis.none")} count={data.decided} />
      <BenchmarkPanel bench={bench}>
        <Pair items={[{ label: t("kpi3.top1"), value: pct(bench.values.top1_percent ?? null) }, { label: t("kpi3.topk"), value: pct(bench.values.topk_percent ?? null) }]} />
      </BenchmarkPanel>
    </>
  );
}

function Kpi4({ data, bench }: { data: KpiReport["kpi4_calibration"]; bench: KpiBenchmark }) {
  const { t } = useI18n();
  const verdict = data.ordered === true
    ? { icon: <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />, text: t("kpi4.ordered_yes") }
    : data.ordered === false
      ? { icon: <AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />, text: t("kpi4.ordered_no") }
      : { icon: <Info className="h-4 w-4 text-muted" aria-hidden="true" />, text: t("kpi4.ordered_none") };
  return (
    <>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{t("kpis.live")} · {t("kpi4.axis")}</p>
      {data.decisions > 0 ? (
        <BarList caption={t("kpi4.title")} max={100} bars={data.levels.map((level) => ({
          label: t(`confidence.${level.level}`),
          value: level.approved_percent ?? 0,
          display: level.decisions ? `${pct(level.approved_percent)} (${level.approved}/${level.decisions})` : "—",
          tip: t("kpi4.bar", { level: t(`confidence.${level.level}`), approved: level.approved, decisions: level.decisions }),
        }))} />
      ) : <p className="text-sm text-muted">{t("kpis.none")}</p>}
      <Basis text={t("kpis.decisions", { count: data.decisions })} count={data.decisions} />
      <p className="mt-3 flex items-start gap-2 text-sm text-ink">{verdict.icon}{verdict.text}</p>
      <BenchmarkPanel bench={bench}>
        <p className="text-4xl font-semibold tracking-tight text-ink">{pct(bench.values.calibration_percent ?? null)}</p>
      </BenchmarkPanel>
    </>
  );
}

function Trend({ weeks }: { weeks: KpiReport["weeks"] }) {
  const { t, language } = useI18n();
  const legend = [
    { label: t("kpis.trend.validated"), value: 0, colour: SERIES.blue },
    { label: t("kpis.trend.rejected"), value: 0, colour: SERIES.orange },
    { label: t("kpis.trend.other"), value: 0, colour: SERIES.aqua },
  ];
  return (
    <Card className="p-5 sm:p-6">
      <h2 className="mb-4 text-lg font-semibold text-ink">{t("kpis.trend")}</h2>
      {weeks.length === 0 ? <p className="text-sm text-muted">{t("kpis.none")}</p> : (
        <Columns caption={t("kpis.trend")} legend={legend} columns={weeks.map((week) => ({
          key: formatDate(week.week, language).replace(/\s\d{4}$/, ""),
          label: t("kpis.trend.week", { date: formatDate(week.week, language) }),
          parts: [
            { label: legend[0]!.label, value: week.validated, colour: SERIES.blue },
            { label: legend[1]!.label, value: week.rejected, colour: SERIES.orange },
            { label: legend[2]!.label, value: week.started - week.validated - week.rejected, colour: SERIES.aqua },
          ],
        }))} />
      )}
    </Card>
  );
}

export function KpisPage() {
  const { t } = useI18n();
  const { value, set } = useUrlState(DEFAULTS);
  const period = (PERIODS as string[]).includes(value("period")) ? (value("period") as Period) : "all";
  const kpis = useKpis(startOf(period));
  const data = kpis.data;

  return (
    <>
      <PageHeader title={t("kpis.title")} subtitle={t("kpis.subtitle")} />
      <div className="flex flex-wrap items-center gap-3">
        <PillTabs label={t("kpis.period")} value={period} onChange={(next) => set({ period: next })}
                  tabs={PERIODS.map((item) => ({ value: item, label: t(`kpis.period.${item}`) }))} />
      </div>
      <p className="mt-2 text-xs text-muted">{t("kpis.period_note")}</p>

      {kpis.isError && !data && <div className="mt-6"><ErrorState error={kpis.error} title={t("kpis.load_error")} onRetry={() => void kpis.refetch()} /></div>}
      {!data && kpis.isPending && (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">{[0, 1, 2, 3].map((key) => <Skeleton key={key} className="h-80 rounded-card" />)}</div>
      )}

      {data && (
        <div className={clsx("mt-6 flex flex-col gap-6 transition-opacity", kpis.isPlaceholderData && "opacity-60")} aria-busy={kpis.isFetching}>
          <section aria-label={t("kpis.now")}>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
              <StatTile label={t("kpis.now.open")} value={data.overview.problems.Open} />
              <StatTile label={t("kpis.now.investigation")} value={data.overview.problems["In investigation"]} />
              <StatTile label={t("kpis.now.manual")} value={data.overview.problems.Manual} tone={data.overview.problems.Manual ? "danger" : undefined} />
              <StatTile label={t("kpis.now.awaiting")} value={data.overview.awaiting_review} tone={data.overview.awaiting_review ? "warning" : undefined} />
              <StatTile label={t("kpis.now.median")} value={duration(data.overview.median_hours_to_decision, t)} />
            </div>
          </section>

          <div className="grid gap-6 lg:grid-cols-2">
            <KpiCard tag="kpi1.tag" title="kpi1.title" question="kpi1.question" how="kpi1.how" read="kpi1.read" icon={<Scale className="h-5 w-5" aria-hidden="true" />}>
              <Kpi1 data={data.kpi1_interactions} />
            </KpiCard>
            <KpiCard tag="kpi2.tag" title="kpi2.title" question="kpi2.question" how="kpi2.how" read="kpi2.read" icon={<CheckCircle2 className="h-5 w-5" aria-hidden="true" />}>
              <Kpi2 data={data.kpi2_autonomy} />
            </KpiCard>
            <KpiCard tag="kpi3.tag" title="kpi3.title" question="kpi3.question" how="kpi3.how" read="kpi3.read" icon={<FlaskConical className="h-5 w-5" aria-hidden="true" />}>
              <Kpi3 data={data.kpi3_accuracy} bench={data.benchmark.accuracy} />
            </KpiCard>
            <KpiCard tag="kpi4.tag" title="kpi4.title" question="kpi4.question" how="kpi4.how" read="kpi4.read" icon={<HelpCircle className="h-5 w-5" aria-hidden="true" />}>
              <Kpi4 data={data.kpi4_calibration} bench={data.benchmark.calibration} />
            </KpiCard>
          </div>

          <Trend weeks={data.weeks} />
        </div>
      )}
    </>
  );
}
