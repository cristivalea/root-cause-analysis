import { Link } from "react-router-dom";
import { clsx } from "clsx";
import { useMemo } from "react";
import { AlertTriangle, ArrowRight, FolderSearch, Lightbulb, MessageSquareText, Send } from "lucide-react";
import { useUser } from "@/auth/AuthProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { useProblems, useRcas, useSummaries } from "@/api/queries";
import type { RCARecord } from "@/api/types";
import { Card, Id } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import { Pill } from "@/components/ui/Pills";
import { formatDateTime } from "@/lib/format";
import { Hero } from "./HomeParts";

function EntryCard({ to, title, text, icon: Icon, badge }: {
  to: string; title: string; text: string; icon: typeof FolderSearch; badge?: React.ReactNode;
}) {
  return (
    <Link to={to}
          className="group flex items-start gap-3 rounded-card bg-white/10 p-4 text-white ring-1 ring-white/10 transition-colors hover:bg-white/15">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-sky-300 text-brand-950">
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

type TodoKind = "ready" | "more" | "failed";
const TODO_ICON: Record<TodoKind, typeof Send> = { ready: Send, more: MessageSquareText, failed: AlertTriangle };
const TODO_TONE: Record<TodoKind, string> = {
  ready: "bg-brand-100 text-brand-700", more: "bg-info-soft text-info", failed: "bg-danger-soft text-danger",
};
const SHOWN = 4;

/** One list of "To do now": the analyses waiting for one step of the Problem Manager, newest first, each
 * opening its investigation, where that step is. */
function TodoCard({ kind, items, loading, titles }: {
  kind: TodoKind; items: RCARecord[]; loading: boolean; titles: Map<string, string>;
}) {
  const { t, language } = useI18n();
  const Icon = TODO_ICON[kind];
  return (
    <Card className="flex flex-col p-5">
      <div className="flex items-start gap-3">
        <span className={clsx("flex h-9 w-9 shrink-0 items-center justify-center rounded-control", TODO_TONE[kind])}>
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="flex items-center gap-2 font-semibold text-ink">
            {t(`home.todo.${kind}`)}
            {!loading && <span className="tabular rounded-full bg-neutral-soft px-2 text-xs text-muted">{items.length}</span>}
          </h3>
          <p className="mt-0.5 text-xs text-muted">{t(`home.todo.${kind}_text`)}</p>
        </div>
      </div>
      <ul className="mt-4 flex flex-col gap-1.5">
        {loading && [0, 1].map((key) => <li key={key}><Skeleton className="h-12 rounded-control" /></li>)}
        {!loading && items.length === 0 && <li className="rounded-control bg-neutral-soft px-3 py-3 text-center text-sm text-muted">{t("home.todo.none")}</li>}
        {items.slice(0, SHOWN).map((record) => (
          <li key={record.rca_id}>
            <Link to={`/investigation/${record.rca_id}`}
                  className="group flex items-center gap-2 rounded-control border border-line px-3 py-2 transition-colors hover:border-brand-600/40 hover:bg-brand-50">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-ink" title={titles.get(record.rca_id)}>{titles.get(record.rca_id) ?? record.rca_id}</span>
                <span className="block text-xs text-muted">{formatDateTime(record.created_at, language)}</span>
              </span>
              <ArrowRight className="h-4 w-4 shrink-0 text-brand-700 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
            </Link>
          </li>
        ))}
      </ul>
      {items.length > SHOWN && (
        <Link to="/history" className="mt-2 text-xs font-semibold text-brand-700 hover:underline">{t("home.todo.more_count", { count: items.length - SHOWN })}</Link>
      )}
    </Card>
  );
}

/** "To do now": what waits for the Problem Manager (send, redo, try again), and a line on what waits for
 * others (running, with the expert). Read from the statuses the API reports; nothing is guessed. */
function Todo() {
  const { t } = useI18n();
  const drafts = useRcas("DRAFT");
  const more = useRcas("REQUEST_MORE_DETAILS");
  const failed = useRcas("FAILED");
  const awaiting = useRcas("AWAITING_TECHNICAL_REVIEW");
  const summaries = useSummaries();
  const titles = useMemo(() => new Map((summaries.data ?? []).map((item) => [item.rca_id, item.title])), [summaries.data]);
  const newest = (items: RCARecord[] | undefined) => [...(items ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const ready = newest(drafts.data?.filter((record) => record.run_status === "COMPLETED"));
  const running = drafts.data?.filter((record) => record.run_status === "RUNNING").length;
  const loading = drafts.isPending || more.isPending || failed.isPending;
  const nothing = !loading && ready.length === 0 && (more.data ?? []).length === 0 && (failed.data ?? []).length === 0;
  return (
    <section aria-labelledby="todo-title">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="todo-title" className="text-xl font-semibold tracking-tight text-ink">{t("home.todo_title")}</h2>
          <p className="mt-1 text-sm text-muted">{nothing ? t("home.todo.all_clear") : t("home.todo_sub")}</p>
        </div>
        {running !== undefined && awaiting.data && (
          <p className="text-sm text-muted">{t("home.todo.elsewhere", { running, awaiting: awaiting.data.length })}</p>
        )}
      </div>
      {(drafts.isError || more.isError || failed.isError) && <p className="mt-3 text-sm text-danger">{t("error.load")}</p>}
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <TodoCard kind="ready" items={ready} loading={loading} titles={titles} />
        <TodoCard kind="more" items={newest(more.data)} loading={loading} titles={titles} />
        <TodoCard kind="failed" items={newest(failed.data)} loading={loading} titles={titles} />
      </div>
    </section>
  );
}

function ManagerHome({ name }: { name: string }) {
  const { t } = useI18n();
  const problems = useProblems();
  const open = problems.data?.filter((item) => item.status === "Open").length;
  return (
    <div className="flex flex-col gap-8">
      <Hero name={name} intro="home.pm.intro">
        <EntryCard to="/problems" title={t("home.go_problems")} text={t("home.problems_text")} icon={FolderSearch}
                   badge={open !== undefined && <Pill tone="brand" className="bg-white/90">{t("home.open_count", { count: open })}</Pill>} />
        <EntryCard to="/proposals" title={t("home.go_proposals")} text={t("home.proposals_text")} icon={Lightbulb} />
      </Hero>
      <Todo />
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
    <div className="flex flex-col gap-8">
      <Hero name={name} intro="home.te.intro" />
      <Waiting />
    </div>
  );
}

export function HomePage() {
  const user = useUser();
  return user.role === "problem_manager" ? <ManagerHome name={user.username} /> : <ExpertHome name={user.username} />;
}
