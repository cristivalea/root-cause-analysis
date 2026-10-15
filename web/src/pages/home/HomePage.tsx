import { Link } from "react-router-dom";
import { clsx } from "clsx";
import { ArrowRight, BookCheck, ClipboardCheck, FileSearch, FolderSearch, Lightbulb, ListChecks, Microscope, PlayCircle, Search, Send } from "lucide-react";
import { useUser } from "@/auth/AuthProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { useProblems, useRcas, useSummaries } from "@/api/queries";
import { Card, Id } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import { Pill } from "@/components/ui/Pills";
import { DiagramFrame } from "@/components/rca/DiagramFrame";
import { FiveWhysDiagram } from "@/components/rca/FiveWhysDiagram";
import { formatDateTime } from "@/lib/format";
import { Claims, Hero, ProcessSteps, type Step } from "./HomeParts";

const PM_STEPS: Step[] = [
  { title: "home.pm.step1.title", text: "home.pm.step1.text", icon: Lightbulb },
  { title: "home.pm.step2.title", text: "home.pm.step2.text", icon: PlayCircle },
  { title: "home.pm.step3.title", text: "home.pm.step3.text", icon: Search },
  { title: "home.pm.step4.title", text: "home.pm.step4.text", icon: ListChecks },
  { title: "home.pm.step5.title", text: "home.pm.step5.text", icon: Send },
];

const TE_STEPS: Step[] = [
  { title: "home.te.step1.title", text: "home.te.step1.text", icon: ClipboardCheck },
  { title: "home.te.step2.title", text: "home.te.step2.text", icon: Microscope },
  { title: "home.te.step3.title", text: "home.te.step3.text", icon: FileSearch },
  { title: "home.te.step4.title", text: "home.te.step4.text", icon: BookCheck },
];

function EntryCard({ to, title, text, icon: Icon, badge }: {
  to: string; title: string; text: string; icon: typeof FolderSearch; badge?: React.ReactNode;
}) {
  return (
    <Link to={to}
          className="group flex items-start gap-3 rounded-card bg-white/10 p-4 text-white ring-1 ring-white/10 transition-colors hover:bg-white/15">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-emerald-300 text-brand-950">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 font-semibold">
          {title}
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
        </span>
        <span className="mt-0.5 block text-sm text-white/70">{text}</span>
        {badge && <span className="mt-2 block">{badge}</span>}
      </span>
    </Link>
  );
}

/** "Move from symptoms toward explanations", with a small labelled example of a 5 Whys diagram. */
function Symptoms() {
  const { t } = useI18n();
  const evidence = (id: string, label: string) => [{ id, label }];
  return (
    <section aria-labelledby="symptoms-title" className="grid grid-cols-[minmax(0,1fr)] items-center gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div>
        <h2 id="symptoms-title" className="text-xl font-semibold tracking-tight text-ink">{t("home.symptoms_title")}</h2>
        <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-muted">{t("home.symptoms_text")}</p>
      </div>
      <div className="relative">
        <Pill tone="brand" className="absolute left-3 top-3 z-10">{t("home.example")}</Pill>
        <DiagramFrame label={t("diagram.example_label")} maxHeight={540} className="bg-surface">
          <FiveWhysDiagram
            problem={t("home.example_problem")}
            steps={[
              { text: t("home.example_why1"), evidence: evidence("1", t("home.example_ev1")) },
              { text: t("home.example_why3"), evidence: evidence("3", t("home.example_ev3")) },
            ]}
            root={t("home.example_root")}
            rootLabel={t("diagram.root_cause")}
          />
        </DiagramFrame>
      </div>
    </section>
  );
}

function ManagerHome({ name }: { name: string }) {
  const { t } = useI18n();
  const problems = useProblems();
  const open = problems.data?.filter((item) => item.status === "Open").length;
  return (
    <div className="flex flex-col gap-12">
      <Hero name={name} intro="home.pm.intro">
        <EntryCard to="/problems" title={t("home.go_problems")} text={t("home.problems_text")} icon={FolderSearch}
                   badge={open !== undefined && <Pill tone="brand" className="bg-white/90">{t("home.open_count", { count: open })}</Pill>} />
        <EntryCard to="/proposals" title={t("home.go_proposals")} text={t("home.proposals_text")} icon={Lightbulb} />
      </Hero>
      <ProcessSteps title="home.how_title" subtitle="home.how_sub" steps={PM_STEPS} />
      <Symptoms />
      <Claims />
    </div>
  );
}

/** What waits for the expert: the RCAs in AWAITING_TECHNICAL_REVIEW, newest first. This is the real review
 * status the API reports; the application has no push notifications and none are simulated. */
function Waiting() {
  const { t, language } = useI18n();
  const waiting = useRcas("AWAITING_TECHNICAL_REVIEW");
  const summaries = useSummaries();
  const titles = new Map(summaries.data?.map((item) => [item.rca_id, item.title]));
  const items = [...(waiting.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at));
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
          {t("home.waiting_title")}
          {waiting.data && <span className="tabular rounded-full bg-warning-soft px-2 text-sm text-warning">{items.length}</span>}
        </h2>
        <Link to="/review" className="text-sm font-semibold text-brand-700 hover:underline">{t("home.waiting_all")}</Link>
      </div>
      <div className="mt-4 flex flex-col gap-2">
        {waiting.isPending && [0, 1].map((key) => <Skeleton key={key} className="h-16 rounded-card" />)}
        {waiting.isError && <p className="text-sm text-danger">{t("error.load")}</p>}
        {waiting.data && items.length === 0 && <p className="rounded-card bg-neutral-soft px-4 py-5 text-center text-sm text-muted">{t("home.waiting_none")}</p>}
        {items.slice(0, 5).map((record) => (
          <Link key={record.rca_id} to={`/review/${record.rca_id}`}
                className="group flex flex-wrap items-center gap-x-4 gap-y-1 rounded-card border border-line px-4 py-3 transition-colors hover:border-brand-600/40 hover:bg-brand-50">
            <span className={clsx("h-2.5 w-2.5 shrink-0 rounded-full", record.revision > 1 ? "bg-info" : "bg-warning")} aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-ink">{titles.get(record.rca_id) ?? record.rca_id}</span>
              <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
                <Id>{record.rca_id}</Id>·<Id>{record.problem_id}</Id>·
                <span>{record.revision > 1 ? t("home.waiting_revision", { revision: record.revision }) : t("home.waiting_new")}</span>·
                <span>{formatDateTime(record.created_at, language)}</span>
              </span>
            </span>
            <span className="inline-flex items-center gap-1 text-sm font-semibold text-brand-700">
              {t("home.review")}
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
            </span>
          </Link>
        ))}
      </div>
    </Card>
  );
}

function ExpertHome({ name }: { name: string }) {
  return (
    <div className="flex flex-col gap-12">
      <Hero name={name} intro="home.te.intro" />
      <Waiting />
      <ProcessSteps title="home.te.how_title" steps={TE_STEPS} />
      <Claims />
    </div>
  );
}

export function HomePage() {
  const user = useUser();
  return user.role === "problem_manager" ? <ManagerHome name={user.username} /> : <ExpertHome name={user.username} />;
}
