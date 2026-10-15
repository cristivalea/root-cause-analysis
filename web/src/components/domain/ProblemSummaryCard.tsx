import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Info, Layers } from "lucide-react";
import { useIncident } from "@/api/queries";
import type { Incident } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { IconButton } from "@/components/ui/Button";
import { Card, Id } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { Skeleton } from "@/components/ui/States";

function IncidentTitle({ id, known }: { id: string; known?: Incident }) {
  const fetched = useIncident(known ? null : id);
  const title = known?.title ?? fetched.data?.title;
  if (title) return <span className="min-w-0 flex-1 truncate text-sm text-ink" title={title}>{title}</span>;
  return fetched.isPending && !known ? <Skeleton className="h-4 flex-1" /> : <span className="flex-1" />;
}

/** The problem an analysis is about: its id and title, the way to it, and its incidents folded underneath. */
export function ProblemSummaryCard({ problemId, title, incidentIds, index, onDetails, badges, linkToProblem = true, children }: {
  problemId: string;
  title: string;
  incidentIds: string[];
  index?: Map<string, Incident>;
  onDetails: (incidentId: string) => void;
  badges?: ReactNode;
  linkToProblem?: boolean;
  children?: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 bg-gradient-to-r from-brand-50 to-surface px-5 py-5 sm:px-6">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2"><Id>{problemId}</Id>{badges}</div>
          <h1 className="mt-1.5 text-xl font-semibold leading-snug tracking-tight text-ink sm:text-2xl">{title}</h1>
        </div>
        {linkToProblem && (
          <Link to={`/problems/${problemId}`}
                className="inline-flex h-9 items-center gap-1.5 rounded-control border border-line bg-surface px-3 text-sm font-medium text-ink shadow-card hover:border-brand-600/40 hover:bg-brand-50">
            {t("inv.open_problem")}<ArrowUpRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        )}
      </div>
      <div className="border-t border-line px-5 py-3 sm:px-6">
        <Disclosure label={t("inv.incidents")} count={incidentIds.length} icon={<Layers className="h-4 w-4" aria-hidden="true" />}>
          <ul className="grid gap-1 pb-1 sm:grid-cols-2">
            {incidentIds.map((id) => (
              <li key={id} className="flex min-w-0 items-center gap-3 rounded-control px-2 py-1.5 hover:bg-brand-50/60">
                <Id>{id}</Id>
                <IncidentTitle id={id} known={index?.get(id)} />
                <IconButton label={t("problem.details", { id })} onClick={() => onDetails(id)}><Info className="h-4 w-4" aria-hidden="true" /></IconButton>
              </li>
            ))}
          </ul>
        </Disclosure>
        {children}
      </div>
    </Card>
  );
}
