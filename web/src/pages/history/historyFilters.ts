import { revisionId, type RCARecord, type RCAStatus, type RCASummary } from "@/api/types";
import { dayOf } from "@/lib/format";

export interface HistoryFilters {
  query: string;
  status: RCAStatus | "";
  service: string;
  from: string;
  to: string;
}

/** The incidents an RCA looked at, over all its revisions. */
export function incidentsOf(revisions: RCARecord[]): string[] {
  return [...new Set(revisions.flatMap((record) => [record.incident_id, ...(record.context?.incident_ids ?? [])]))];
}

/** Search over the RCA, its problem, its title, its revision ids and the incidents of its revisions. */
export function filterHistory(rcas: RCASummary[], revisions: Map<string, RCARecord[]>, servicesOf: Map<string, string[]>, filters: HistoryFilters) {
  const needle = filters.query.trim().toLowerCase();
  return rcas.filter((rca) => {
    const runs = revisions.get(rca.rca_id) ?? [];
    const text = !needle || [rca.rca_id, rca.problem_id, rca.title, ...runs.map(revisionId), ...incidentsOf(runs)]
      .some((value) => value.toLowerCase().includes(needle));
    const services = servicesOf.get(rca.problem_id) ?? runs.flatMap((record) => record.context?.services ?? []);
    return text &&
      (!filters.status || rca.status === filters.status) &&
      (!filters.service || services.includes(filters.service)) &&
      (!filters.from || dayOf(rca.created_at) >= filters.from) &&
      (!filters.to || dayOf(rca.created_at) <= filters.to);
  });
}
