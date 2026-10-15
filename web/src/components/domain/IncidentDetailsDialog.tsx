import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useIncident, useRcas, useTeams } from "@/api/queries";
import type { Incident } from "@/api/types";
import { useI18n } from "@/i18n/I18nProvider";
import { Dialog } from "@/components/ui/Dialog";
import { Id } from "@/components/ui/Card";
import { Pill, RcaStatusPill, SeverityPill } from "@/components/ui/Pills";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { formatDateTime, formatMinutes, formatNumber } from "@/lib/format";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-muted">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-ink">{children || "—"}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-line pt-4">
      <h3 className="mb-3 text-sm font-semibold text-ink">{title}</h3>
      {children}
    </section>
  );
}

function PastAnalyses({ incidentId, linkable }: { incidentId: string; linkable: boolean }) {
  const { t, language } = useI18n();
  const rcas = useRcas();
  if (rcas.isPending) return <Skeleton className="h-6 w-2/3" />;
  const found = (rcas.data ?? []).filter((record) =>
    record.incident_id === incidentId || record.context?.incident_ids.includes(incidentId));
  if (found.length === 0) return <p className="text-sm text-muted">{t("incident.past_none")}</p>;
  return (
    <ul className="flex flex-col gap-2">
      {found.map((record) => (
        <li key={record.rca_id} className="flex flex-wrap items-center gap-2 text-sm">
          {linkable ? <Link to={`/investigation/${record.rca_id}`} className="font-medium text-brand-700 hover:underline">{record.rca_id}</Link> : <Id>{record.rca_id}</Id>}
          <RcaStatusPill status={record.status} />
          <span className="text-muted">{formatDateTime(record.created_at, language)}</span>
        </li>
      ))}
    </ul>
  );
}

function Details({ incident, linkable }: { incident: Incident; linkable: boolean }) {
  const { t, language } = useI18n();
  const teams = useTeams(incident.service);
  const impact = incident.impact;
  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <SeverityPill severity={incident.severity} />
          <Pill tone="neutral">{incident.status}</Pill>
        </div>
        <h3 className="mt-3 text-base font-semibold text-ink">{incident.title}</h3>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">{incident.description}</p>
      </div>

      {(incident.symptoms.length > 0 || incident.initial_mitigation) && (
        <Section title={t("incident.symptoms")}>
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink">
            {incident.symptoms.map((symptom) => <li key={symptom}>{symptom}</li>)}
          </ul>
          {incident.initial_mitigation && (
            <dl className="mt-3"><Fact label={t("incident.mitigation")}>{incident.initial_mitigation}</Fact></dl>
          )}
        </Section>
      )}

      <Section title={t("incident.service")}>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Fact label={t("incident.service")}>{incident.service}</Fact>
          <Fact label={t("incident.business_service")}>{incident.business_service}</Fact>
          <Fact label={t("incident.environment")}>{incident.environment}</Fact>
          <Fact label={t("incident.teams")}>{teams.data?.join(", ")}</Fact>
          <Fact label={t("incident.detected")}>{formatDateTime(incident.detected_at, language)}</Fact>
          <Fact label={t("incident.resolved")}>{formatDateTime(incident.resolved_at, language)}</Fact>
          <Fact label={t("incident.duration")}>{formatMinutes(incident.duration_minutes, t)}</Fact>
        </dl>
      </Section>

      {(impact || incident.affected_regions.length > 0) && (
        <Section title={t("incident.impact")}>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Fact label={t("incident.failed_transactions")}>{formatNumber(impact?.failed_transactions, language)}</Fact>
            <Fact label={t("incident.customers")}>{formatNumber(impact?.estimated_customers_affected, language)}</Fact>
            <Fact label={t("incident.error_rate")}>{impact?.error_rate_peak}</Fact>
            <Fact label={t("incident.regions")}>{incident.affected_regions.join(", ")}</Fact>
          </dl>
        </Section>
      )}

      {(incident.rca_reason || incident.reported_by) && (
        <Section title={t("incident.why_rca")}>
          {incident.rca_reason && <p className="text-sm text-ink">{incident.rca_reason}</p>}
          {incident.reported_by && <p className="mt-1 text-xs text-muted">{t("incident.reported_by")}: {incident.reported_by}</p>}
        </Section>
      )}

      <Section title={t("incident.past")}>
        <PastAnalyses incidentId={incident.incident_id} linkable={linkable} />
      </Section>
    </div>
  );
}

/** Everything known about one incident, in a dialog over the page. The incident comes from the list already
 * loaded when there is one, else from GET /incidents/{id}. */
export function IncidentDetailsDialog({ incidentId, known, onClose, linkable = true }: {
  incidentId: string | null;
  known?: Incident;
  onClose: () => void;
  linkable?: boolean;
}) {
  const { t } = useI18n();
  const fetched = useIncident(known ? null : incidentId);
  const incident = known ?? fetched.data;
  return (
    <Dialog open={incidentId !== null} onOpenChange={(open) => !open && onClose()} size="lg"
            title={<span className="flex items-center gap-2">{t("incident.title")} <Id>{incidentId}</Id></span>}>
      {incident && <Details incident={incident} linkable={linkable} />}
      {!incident && fetched.isPending && <div className="flex flex-col gap-3"><Skeleton className="h-6 w-1/3" /><Skeleton className="h-20" /></div>}
      {!incident && fetched.isError && <ErrorState error={fetched.error} title={t("incident.unavailable")} />}
    </Dialog>
  );
}
