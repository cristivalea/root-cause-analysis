import { vi } from "vitest";
import type { Incident, Problem, ProblemDetail, RCARecord } from "@/api/types";
import { jsonResponse } from "./render";

export function problem(index: number, change: Partial<Problem> = {}): Problem {
  const id = `PRB-2026-${String(index).padStart(5, "0")}`;
  return {
    problem_id: id, title: `Problem number ${index}`, description: "", status: "Open", priority: "P2",
    services: ["Payment API"], created_at: `2026-0${(index % 9) + 1}-10T10:00:00+00:00`, created_by: "manager",
    closed_at: null, close_reason: null, rca_id: null, guidance: null,
    incidents: [{ incident_id: `INC-2026-${String(index).padStart(5, "0")}`, linked_at: "2026-10-01T10:00:00+00:00", linked_by: "manager" }],
    ...change,
  };
}

export function incident(id: string, change: Partial<Incident> = {}): Incident {
  return {
    incident_id: id, title: `Incident ${id}`, description: "It broke.", severity: "SEV-2", status: "Resolved",
    service: "Payment API", business_service: "Payments", environment: "production", detected_at: "2026-10-01T10:00:00+00:00",
    resolved_at: null, duration_minutes: 40, affected_regions: [], impact: null, symptoms: ["Slow"], initial_mitigation: null,
    reported_by: null, rca_required: true, rca_reason: null, ...change,
  };
}

export function rca(change: Partial<RCARecord> = {}): RCARecord {
  return {
    rca_id: "RCA-2026-00001", revision: 1, previous_revision_id: null, run_status: "COMPLETED", error: null,
    incident_id: "INC-2026-00001", status: "DRAFT", owner: "manager", created_at: "2026-10-02T10:00:00+00:00",
    completed_at: null, duration_seconds: 30, linked_incidents: [], problem_id: "PRB-2026-00001", guidance: null,
    current_step: null, context: null, plan: null, evidence: [], timeline: [], trace: [], investigation_summary: "",
    observed_patterns: [], hypotheses: [], single_hypothesis_reason: null, not_checked: [], weakly_supported: false,
    suggested_workaround: null, change_likely_required: false, review: null, final_root_cause: null, review_rounds: 0,
    ...change,
  };
}

export const detail = (value: Problem, rcas: RCARecord[] = []): ProblemDetail => ({ problem: value, events: [], rcas });

type Handler = (body: unknown) => unknown | Response;

/** A fake API: "GET /problems" → answer. Every request is recorded; an unknown one fails the test loudly. */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = new URL(String(input), "http://localhost");
    const method = init?.method ?? "GET";
    const path = url.pathname.replace("/api/v1", "") + url.search;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });
    const route = routes[`${method} ${path}`];
    if (route === undefined) return jsonResponse({ detail: `no mock for ${method} ${path}` }, 599);
    const answer = typeof route === "function" ? (route as Handler)(body) : route;
    return answer instanceof Response ? answer : jsonResponse(answer);
  });
  return calls;
}
