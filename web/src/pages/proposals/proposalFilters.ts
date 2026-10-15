import type { Incident, Proposal, ProposalKind, Severity } from "@/api/types";
import { dayOf } from "@/lib/format";

export interface IncidentFilters {
  query: string;
  service: string;
  severity: Severity | "";
  from: string;
  to: string;
}

export interface ProposalFilters extends IncidentFilters {
  kind: ProposalKind;
  minScore: number; // 0 to 100, in percent of the stored 0–1 score
}

function incidentMatches(incident: Incident | undefined, filters: IncidentFilters): boolean {
  if (!incident) return !filters.service && !filters.severity && !filters.from && !filters.to;
  const day = dayOf(incident.detected_at);
  return (!filters.service || incident.service === filters.service) &&
    (!filters.severity || incident.severity === filters.severity) &&
    (!filters.from || day >= filters.from) &&
    (!filters.to || day <= filters.to);
}

/** A proposal is kept when its text matches and at least one of its incidents passes the incident filters. */
export function filterProposals(proposals: Proposal[], incidents: Map<string, Incident>, filters: ProposalFilters): Proposal[] {
  const needle = filters.query.trim().toLowerCase();
  return proposals.filter((proposal) => {
    if (proposal.kind !== filters.kind) return false;
    if (filters.minScore > 0 && (proposal.score === null || proposal.score * 100 < filters.minScore)) return false;
    const members = proposal.incident_ids.map((id) => incidents.get(id));
    const text = !needle || proposal.problem_id?.toLowerCase().includes(needle) ||
      proposal.incident_ids.some((id, index) => id.toLowerCase().includes(needle) || members[index]?.title.toLowerCase().includes(needle));
    return text && members.some((member) => incidentMatches(member, filters));
  });
}

export function filterIncidents(items: Incident[], filters: IncidentFilters): Incident[] {
  const needle = filters.query.trim().toLowerCase();
  return items.filter((incident) =>
    (!needle || incident.incident_id.toLowerCase().includes(needle) || incident.title.toLowerCase().includes(needle)) &&
    incidentMatches(incident, filters));
}

export function countByKind(proposals: Proposal[]): Record<ProposalKind, number> {
  const counts: Record<ProposalKind, number> = { group: 0, attach: 0, single: 0 };
  for (const proposal of proposals) counts[proposal.kind] += 1;
  return counts;
}
