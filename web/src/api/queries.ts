import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post, put } from "./client";
import type {
  Candidate, Incident, InvestigationGuidance, Problem, ProblemDetail, ProblemResult, Proposal, RCARecord, RCASummary, RCAStatus, RCAStatusChange, DiagramData, Comparison, KpiReport,
} from "./types";

/** Cache keys, one place: a change invalidates exactly what it can have changed. */
export const keys = {
  problems: ["problems"] as const,
  problem: (id: string) => ["problem", id] as const,
  incidents: ["incidents"] as const,
  incident: (id: string) => ["incident", id] as const,
  unassigned: ["incidents", "unassigned"] as const,
  candidates: (problemId: string) => ["candidates", problemId] as const,
  services: ["services"] as const,
  teams: (service: string) => ["teams", service] as const,
  rcas: (status?: RCAStatus) => ["rcas", status ?? "all"] as const,
  summaries: ["rcas", "summaries"] as const,
  proposals: ["proposals"] as const,
};

const FIVE_MINUTES = 5 * 60_000;

export const useProblems = () => useQuery({ queryKey: keys.problems, queryFn: ({ signal }) => get<Problem[]>("/problems", signal) });

export const useProblem = (id: string) =>
  useQuery({ queryKey: keys.problem(id), queryFn: ({ signal }) => get<ProblemDetail>(`/problems/${encodeURIComponent(id)}`, signal), enabled: Boolean(id) });

/** Every incident (Problem Manager only): read once, used for titles everywhere. Incidents never change. */
export const useIncidents = (enabled = true) =>
  useQuery({ queryKey: keys.incidents, queryFn: ({ signal }) => get<Incident[]>("/incidents", signal), staleTime: FIVE_MINUTES, enabled });

export function useIncidentIndex(enabled = true): Map<string, Incident> | undefined {
  const { data } = useIncidents(enabled);
  return data ? new Map(data.map((item) => [item.incident_id, item])) : undefined;
}

export const useIncident = (id: string | null) =>
  useQuery({
    queryKey: keys.incident(id ?? ""),
    queryFn: ({ signal }) => get<Incident>(`/incidents/${encodeURIComponent(id!)}`, signal),
    enabled: Boolean(id),
    staleTime: FIVE_MINUTES,
  });

export const useCandidates = (problemId: string, enabled: boolean) =>
  useQuery({
    queryKey: keys.candidates(problemId),
    queryFn: ({ signal }) => get<Candidate[]>(`/problems/${encodeURIComponent(problemId)}/candidates`, signal),
    enabled,
    retry: false, // 503 when the similarity index is missing: the dialog falls back at once
  });

export const useUnassigned = (enabled: boolean) =>
  useQuery({ queryKey: keys.unassigned, queryFn: ({ signal }) => get<Incident[]>("/incidents/unassigned", signal), enabled });

export const useServices = () =>
  useQuery({ queryKey: keys.services, queryFn: ({ signal }) => get<string[]>("/services", signal), staleTime: FIVE_MINUTES });

export const useTeams = (service: string | undefined) =>
  useQuery({
    queryKey: keys.teams(service ?? ""),
    queryFn: ({ signal }) => get<string[]>(`/services/${encodeURIComponent(service!)}/teams`, signal),
    enabled: Boolean(service),
    staleTime: FIVE_MINUTES,
  });

export const useRcas = (status?: RCAStatus, enabled = true) =>
  useQuery({
    queryKey: keys.rcas(status),
    queryFn: ({ signal }) => get<RCARecord[]>(`/rcas${status ? `?status=${status}` : ""}`, signal),
    enabled,
  });

export const useSummaries = () =>
  useQuery({ queryKey: keys.summaries, queryFn: ({ signal }) => get<RCASummary[]>("/rcas/summaries", signal) });

// --------------------------------------------------------------------------------------
// Changes to a problem. Each one goes through the rules of rca/problems.py on the server; the page changes
// only after the server answered, from what it answered.
// --------------------------------------------------------------------------------------

function useProblemChange<V>(problemId: string, request: (variables: V) => Promise<ProblemResult>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (result) => {
      client.setQueryData<ProblemDetail>(keys.problem(problemId), (current) => current && { ...current, problem: result.problem });
      void client.invalidateQueries({ queryKey: keys.problem(problemId) });
      void client.invalidateQueries({ queryKey: keys.problems });
      void client.invalidateQueries({ queryKey: keys.candidates(problemId) });
      void client.invalidateQueries({ queryKey: keys.unassigned });
      void client.invalidateQueries({ queryKey: keys.proposals });
    },
  });
}

const problemPath = (id: string) => `/problems/${encodeURIComponent(id)}`;

export const useAttachIncident = (problemId: string) =>
  useProblemChange(problemId, ({ incidentId, reason }: { incidentId: string; reason?: string }) =>
    post<ProblemResult>(`${problemPath(problemId)}/incidents`, { incident_id: incidentId, reason: reason || null }));

export const useDetachIncident = (problemId: string) =>
  useProblemChange(problemId, ({ incidentId, reason }: { incidentId: string; reason: string }) =>
    post<ProblemResult>(`${problemPath(problemId)}/incidents/${encodeURIComponent(incidentId)}/remove`, { reason }));

export const useSetGuidance = (problemId: string) =>
  useProblemChange(problemId, (guidance: InvestigationGuidance | null) =>
    put<ProblemResult>(`${problemPath(problemId)}/guidance`, { guidance }));

export const useCloseProblem = (problemId: string) =>
  useProblemChange(problemId, (reason: string) => post<ProblemResult>(`${problemPath(problemId)}/close`, { reason }));

export const useReopenProblem = (problemId: string) =>
  useProblemChange(problemId, (reason: string) => post<ProblemResult>(`${problemPath(problemId)}/reopen`, { reason }));

/** Start RCA: the server saves the RCA at once and runs the investigation in the background (202). The same
 * request_key for a repeated click returns the same RCA instead of a second one. */
export function useStartRca(problemId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ guidance, requestKey }: { guidance: InvestigationGuidance | null; requestKey: string }) =>
      post<RCARecord>(`${problemPath(problemId)}/rcas`, { guidance, request_key: requestKey }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.problem(problemId) });
      void client.invalidateQueries({ queryKey: keys.problems });
      void client.invalidateQueries({ queryKey: ["rcas"] });
    },
  });
}

// --------------------------------------------------------------------------------------
// Proposed problems (rca/suggestions.proposals). Slow to compute (~1.6 s): read once per visit, read again
// only after a decision changed them.
// --------------------------------------------------------------------------------------

export const useProposals = () =>
  useQuery({ queryKey: keys.proposals, queryFn: ({ signal }) => get<Proposal[]>("/proposals", signal), staleTime: 2 * 60_000, retry: false });

interface AcceptResult extends ProblemResult {
  created: boolean;
}

function useAfterProblemsChanged() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: keys.proposals });
    void client.invalidateQueries({ queryKey: keys.problems });
    void client.invalidateQueries({ queryKey: keys.unassigned });
    void client.invalidateQueries({ queryKey: ["problem"] });
    void client.invalidateQueries({ queryKey: ["candidates"] });
  };
}

const proposalBody = (proposal: Proposal) => ({
  key: proposal.key, kind: proposal.kind, incident_ids: proposal.incident_ids, problem_id: proposal.problem_id,
});

/** Accept a proposal: the server checks its key and the rules again, and creates the problem (or adds the
 * incident) in one transaction. created is false when an earlier accept already did it. */
export function useAcceptProposal() {
  const refresh = useAfterProblemsChanged();
  return useMutation({
    mutationFn: ({ proposal, title, reason }: { proposal: Proposal; title?: string; reason?: string }) =>
      post<AcceptResult>("/proposals/accept", { ...proposalBody(proposal), title: title || null, reason: reason || null }),
    onSuccess: refresh,
  });
}

export function useRejectProposal() {
  const refresh = useAfterProblemsChanged();
  return useMutation({
    mutationFn: ({ proposal, reason }: { proposal: Proposal; reason: string }) =>
      post<{ key: string; rejected: boolean }>("/proposals/reject", { ...proposalBody(proposal), reason }),
    onSuccess: refresh,
  });
}

/** A problem from incidents the Problem Manager chose: the reason is required by rca/problems.py. */
export function useCreateProblem() {
  const refresh = useAfterProblemsChanged();
  return useMutation({
    mutationFn: ({ incidentIds, title, reason }: { incidentIds: string[]; title?: string; reason: string }) =>
      post<ProblemResult>("/problems", { incident_ids: incidentIds, title: title || null, reason }),
    onSuccess: refresh,
  });
}

// --------------------------------------------------------------------------------------
// One RCA: its revisions, its history, its diagram, and the changes the Problem Manager makes to it.
// --------------------------------------------------------------------------------------

const POLL_MS = 2000;
const rcaPath = (id: string) => `/rcas/${encodeURIComponent(id)}`;

export const rcaKeys = {
  record: (id: string) => ["rca", id] as const,
  revisions: (id: string) => ["rca", id, "revisions"] as const,
  history: (id: string) => ["rca", id, "history"] as const,
  diagram: (id: string) => ["rca", id, "diagram"] as const,
  comparison: (id: string) => ["rca", id, "comparison"] as const,
};

/** A revision (RCA-…-R2) or the latest revision of an RCA (RCA-…). While it runs it is read again every
 * 2 s from what the server saved, step by step; polling stops once the run ended. */
export const useRca = (id: string) =>
  useQuery({
    queryKey: rcaKeys.record(id),
    queryFn: ({ signal }) => get<RCARecord>(rcaPath(id), signal),
    refetchInterval: (query) => (query.state.data?.run_status === "RUNNING" ? POLL_MS : false),
  });

export const useRevisions = (rcaId: string | undefined) =>
  useQuery({
    queryKey: rcaKeys.revisions(rcaId ?? ""),
    queryFn: ({ signal }) => get<RCARecord[]>(`${rcaPath(rcaId!)}/revisions`, signal),
    enabled: Boolean(rcaId),
  });

export const useRcaHistory = (rcaId: string | undefined) =>
  useQuery({
    queryKey: rcaKeys.history(rcaId ?? ""),
    queryFn: ({ signal }) => get<{ rca: RCASummary; history: RCAStatusChange[] }>(`${rcaPath(rcaId!)}/history`, signal),
    enabled: Boolean(rcaId),
  });

/** The cause diagram chosen by rca/diagram.py (read-only route); null when there is nothing to draw. */
export const useDiagram = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: rcaKeys.diagram(id),
    queryFn: ({ signal }) => get<DiagramData | null>(`${rcaPath(id)}/diagram`, signal),
    enabled,
    staleTime: Infinity, // a completed revision never changes
  });

function useAfterRcaChanged() {
  const client = useQueryClient();
  return (record: RCARecord) => {
    void client.invalidateQueries({ queryKey: ["rca"] });
    void client.invalidateQueries({ queryKey: ["rcas"] });
    void client.invalidateQueries({ queryKey: keys.problems });
    if (record.problem_id) void client.invalidateQueries({ queryKey: keys.problem(record.problem_id) });
  };
}

export function useSubmitReview() {
  const refresh = useAfterRcaChanged();
  return useMutation({ mutationFn: (rcaId: string) => post<RCARecord>(`${rcaPath(rcaId)}/submit-review`, {}), onSuccess: refresh });
}

/** The next revision after a request for more details or a failed run. One request key per click. */
export function useStartNextRevision() {
  const refresh = useAfterRcaChanged();
  return useMutation({
    mutationFn: ({ rcaId, requestKey }: { rcaId: string; requestKey: string }) =>
      post<RCARecord>(`${rcaPath(rcaId)}/revisions`, { guidance: null, request_key: requestKey }),
    onSuccess: refresh,
  });
}

/** Every RCA as the list of its revisions (GET /cases), the most recent RCA first. */
export const useCases = () =>
  useQuery({ queryKey: ["rcas", "cases"], queryFn: ({ signal }) => get<RCARecord[][]>("/cases", signal) });

export const useComparison = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: rcaKeys.comparison(id),
    queryFn: ({ signal }) => get<Comparison | null>(`${rcaPath(id)}/comparison`, signal),
    enabled,
    staleTime: Infinity,
  });

export interface ReviewRequest {
  decision: "APPROVE" | "REJECT" | "REQUEST_MORE_DETAILS";
  comment: string;
  hypothesis_id?: string | null;
  requested_checks?: string[] | null;
  guidance?: InvestigationGuidance | null;
}

/** The decision of the Technical Expert (rca/store.apply_review). The reviewer is the signed-in user. */
export function useApplyReview() {
  const refresh = useAfterRcaChanged();
  return useMutation({
    mutationFn: ({ rcaId, review }: { rcaId: string; review: ReviewRequest }) => post<RCARecord>(`${rcaPath(rcaId)}/review`, review),
    onSuccess: refresh,
  });
}

/** The KPIs of a period. While another period loads, the previous numbers stay on screen (dimmed by the page). */
export const useKpis = (from: string | null) =>
  useQuery({
    queryKey: ["kpis", from ?? "all"],
    queryFn: ({ signal }) => get<KpiReport>(`/kpis${from ? `?date_from=${from}` : ""}`, signal),
    placeholderData: (previous) => previous,
  });
