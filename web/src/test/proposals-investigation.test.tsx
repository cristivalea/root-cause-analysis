import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/App";
import { en } from "@/i18n/en";
import type { Evidence, InvestigationStep, Proposal } from "@/api/types";
import { filterProposals } from "@/pages/proposals/proposalFilters";
import { noteText, proposalTexts } from "@/pages/proposals/notes";
import { evidenceSummary } from "@/lib/evidence";
import { format, type Translate } from "@/i18n/I18nProvider";
import { ro } from "@/i18n/ro";
import { stepModels, stepViews } from "@/components/rca/steps";
import { incident, mockApi, problem, rca } from "./fixtures";
import { renderApp, signInAs } from "./render";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
  signInAs("problem_manager", "manager");
});
afterEach(() => vi.restoreAllMocks());

const proposal = (key: string, change: Partial<Proposal>): Proposal => ({
  key, kind: "group", incident_ids: ["INC-2026-00001", "INC-2026-00002"], problem_id: null, score: 0.93,
  reasons: ["Same service."], evidence: ["CMDB item CI-PAY: 2 of 2 incident(s)."], recurrence_of: null,
  score_label: "Text similarity", score_meaning: "Not a probability.", ...change,
});

const incidents = [
  incident("INC-2026-00001", { service: "Payment API", severity: "SEV-1", detected_at: "2026-05-01T10:00:00Z" }),
  incident("INC-2026-00002", { service: "Payment API", detected_at: "2026-06-01T10:00:00Z" }),
  incident("INC-2026-00003", { service: "Auth Service", severity: "SEV-4", detected_at: "2026-07-01T10:00:00Z", title: "Login slow" }),
];

describe("proposal filters", () => {
  const index = new Map(incidents.map((item) => [item.incident_id, item]));
  const list = [proposal("A", {}), proposal("B", { incident_ids: ["INC-2026-00003"], score: 0.86 }), proposal("C", { kind: "single", incident_ids: ["INC-2026-00003"], score: null })];
  const base = { kind: "group" as const, query: "", service: "", severity: "" as const, from: "", to: "", minScore: 0 };

  it("keeps the kind, and filters by service, severity, similarity, period and text", () => {
    expect(filterProposals(list, index, base).map((item) => item.key)).toEqual(["A", "B"]);
    expect(filterProposals(list, index, { ...base, service: "Auth Service" }).map((item) => item.key)).toEqual(["B"]);
    expect(filterProposals(list, index, { ...base, severity: "SEV-1" }).map((item) => item.key)).toEqual(["A"]);
    expect(filterProposals(list, index, { ...base, minScore: 90 }).map((item) => item.key)).toEqual(["A"]);
    expect(filterProposals(list, index, { ...base, from: "2026-06-15" }).map((item) => item.key)).toEqual(["B"]);
    expect(filterProposals(list, index, { ...base, query: "login" }).map((item) => item.key)).toEqual(["B"]);
    expect(filterProposals(list, index, { ...base, kind: "single", minScore: 50 })).toEqual([]); // no score: no similarity to compare
  });
});

describe("Proposed problems page", () => {
  it("shows the similarity in words and rejects only with a reason", async () => {
    const calls = mockApi({
      "GET /proposals": [proposal("PP-1", {})], "GET /incidents": incidents,
      "POST /proposals/reject": { key: "PP-1", rejected: true },
    });
    renderApp(<App />, { route: "/proposals" });
    expect(await screen.findByText("New problem with 2 incidents")).toBeInTheDocument();
    expect(screen.getByText(en["similarity.very"])).toBeInTheDocument();
    expect(screen.queryByText("93%")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["proposals.reject"] }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: en["proposals.reject"] }));
    expect(within(dialog).getByText(en["problem.reason_required"])).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText(/Why you reject it/), "Different causes");
    await userEvent.click(within(dialog).getByRole("button", { name: en["proposals.reject"] }));
    await waitFor(() => expect(calls.find((call) => call.method === "POST")?.body).toEqual({
      key: "PP-1", kind: "group", incident_ids: ["INC-2026-00001", "INC-2026-00002"], problem_id: null, reason: "Different causes",
    }));
  });

  it("creates a problem with the optional title and reason, and says the title rule", async () => {
    const calls = mockApi({
      "GET /proposals": [proposal("PP-1", {})], "GET /incidents": incidents,
      "POST /proposals/accept": { problem: problem(9), warnings: [], created: true },
    });
    renderApp(<App />, { route: "/proposals" });
    await userEvent.click(await screen.findByRole("button", { name: en["proposals.create"] }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(en["proposals.title_hint"])).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: en["proposals.create"] }));
    await waitFor(() => expect(calls.find((call) => call.method === "POST")?.body).toMatchObject({ key: "PP-1", title: null, reason: null }));
    expect(await screen.findByRole("heading", { name: en["success.created_title"] })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["success.open_problem"] })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["success.home"] })).toBeInTheDocument();
  });

  it("offers no Reject for an incident on its own (the server refuses it)", async () => {
    mockApi({ "GET /proposals": [proposal("PP-2", { kind: "single", incident_ids: ["INC-2026-00003"], score: null })], "GET /incidents": incidents });
    renderApp(<App />, { route: "/proposals?tab=single" });
    expect(await screen.findByText("New problem from INC-2026-00003")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["proposals.reject"] })).not.toBeInTheDocument();
  });

  it("creates a problem manually only with a reason", async () => {
    const calls = mockApi({
      "GET /proposals": [proposal("PP-1", {})], "GET /incidents": incidents,
      "POST /problems": { problem: problem(10), warnings: [] },
    });
    renderApp(<App />, { route: "/proposals?tab=manual" });
    await userEvent.click(await screen.findByRole("checkbox", { name: "Select INC-2026-00001" }));
    await userEvent.click(screen.getByRole("button", { name: en["manual.create"] }));
    expect(screen.getByText(en["problem.reason_required"])).toBeInTheDocument();
    expect(calls.some((call) => call.method === "POST")).toBe(false);
    await userEvent.type(screen.getByLabelText(/Why these incidents belong together/), "Same outage");
    await userEvent.click(screen.getByRole("button", { name: en["manual.create"] }));
    await waitFor(() => expect(calls.find((call) => call.method === "POST")?.body).toEqual({ incident_ids: ["INC-2026-00001"], title: null, reason: "Same outage" }));
  });
});

const step = (name: string, details: Record<string, unknown> = {}): InvestigationStep => ({
  name, summary: `${name} done`, started_at: "2026-10-01T10:00:00Z", finished_at: "2026-10-01T10:00:02Z", details,
});

describe("investigation steps", () => {
  it("orders the steps, maps the old names, and places an unknown step where it ran", () => {
    const views = stepViews([step("similar_incidents"), step("investigation_planner"), step("tools")], { running: true, failed: false, current: null });
    expect(views.map((view) => view.name).slice(0, 4)).toEqual(["build_context", "similar_incidents", "investigation_planner", "gather_evidence"]);
    expect(views.find((view) => view.name === "gather_evidence")!.state).toBe("done");
    expect(views.find((view) => view.name === "build_context")!.state).toBe("running"); // the first step not done yet
  });

  it("shows only what a finished run did, and the last run of a repeated step", () => {
    const views = stepViews([step("guardrail", { attempt: 1 }), step("guardrail", { attempt: 2 })], { running: false, failed: false, current: null });
    expect(views).toHaveLength(1);
    expect(views[0]!.runs).toBe(2);
    expect(views[0]!.step!.details.attempt).toBe(2);
  });

  it("names the model only when the step recorded it", () => {
    expect(stepModels(step("rca_reasoning_agent", { models: ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-120b"] })))
      .toEqual([{ provider: "Groq", model: "openai/gpt-oss-120b" }]);
    expect(stepModels(step("guardrail"))).toEqual([]);
  });
});

describe("proposal notes", () => {
  const t: Translate = (key, values) => format(en[key], values);
  const tRo: Translate = (key, values) => format(ro[key], values);

  it("words the reasons and facts plainly, in the language of the interface", () => {
    expect(noteText({ code: "text_alike", params: { incident: "INC-1", title: "Pool exhausted", similarity: 0.95 } }, t, "en"))
      .toBe("The description is very much like that of INC-1: “Pool exhausted”.");
    expect(noteText({ code: "alone", params: { severity: "SEV-3" } }, tRo, "ro")).toContain("gravitate medie");
    expect(noteText({ code: "days_apart", params: { incident: "INC-1", days: 0 } }, tRo, "ro")).toBe("A apărut în aceeași zi cu INC-1.");
    expect(noteText({ code: "severities", params: { counts: { "SEV-1": 2, "SEV-3": 1 } } }, t, "en")).toBe("Severity: critical: 2, medium: 1.");
  });

  it("keeps the English sentence for a code it does not know, and for a server without notes", () => {
    expect(noteText({ code: "something_new", params: {} }, t, "en")).toBeNull();
    const base: Omit<Proposal, "reasons" | "evidence"> = { key: "PP-1", kind: "group", incident_ids: [], problem_id: null, score: null, recurrence_of: null, score_label: "", score_meaning: "" };
    expect(proposalTexts({ ...base, reasons: ["Same service: payments."], evidence: [],
      reason_notes: [{ code: "something_new", params: {} }], evidence_notes: [] }, t, "en").reasons).toEqual(["Same service: payments."]);
    expect(proposalTexts({ ...base, reasons: ["Old text."], evidence: ["Old fact."] }, t, "en")).toEqual({ reasons: ["Old text."], evidence: ["Old fact."] });
  });
});

describe("evidence in plain words", () => {
  const evidence = (type: Evidence["type"], description: string): Evidence =>
    ({ evidence_id: "EV-001", type, source: "x", description, citation: "X-1", timestamp: null, related_ids: [], service: null });

  it("takes the short part of each pattern the code writes, and the start of anything else", () => {
    expect(evidenceSummary(evidence("LOG", '18 ERROR log line(s) of type OOMKilled between 2026-04-04 11:58 and 12:47 UTC, the first 12 minutes before detection.')))
      .toBe("OOMKilled (18×)");
    expect(evidenceSummary(evidence("LOG", "On Auth DB, a dependency: 3 WARN log line(s) of type SlowQuery between …"))).toBe("SlowQuery (3×) · Auth DB");
    expect(evidenceSummary(evidence("CHANGE", "Deploy auth-service Helm chart 5.2.0 on CI-AUTH-APP: Chart upgrade."))).toBe("Deploy auth-service Helm chart 5.2.0");
    expect(evidenceSummary(evidence("CMDB", "auth-service (CI-AUTH-APP) depends_on auth-postgresql (CI-AUTH-DB, database)."))).toBe("auth-service → auth-postgresql");
    expect(evidenceSummary(evidence("INCIDENT", "The incident under investigation, INC-1 on Auth (SEV-1), detected 2026-04-04 12:10 UTC: Auth restarts. More.")))
      .toBe("Auth restarts");
    expect(evidenceSummary(evidence("HISTORICAL_RCA", "Past RCA RCA-2025-00305 for Auth, completed 2025-10-24. Summary: Pods killed for memory. Fixed.")))
      .toBe("Pods killed for memory");
    expect(evidenceSummary(evidence("CHANGE", "Release 4.2"))).toBe("Release 4.2");
    expect(evidenceSummary(evidence("CHANGE", "a".repeat(100)), 20)).toHaveLength(20);
  });
});

describe("Investigation page", () => {
  const record = rca({
    rca_id: "RCA-2026-00005", problem_id: "PRB-2026-00001", status: "DRAFT",
    trace: [step("investigation_planner", { models: ["groq:openai/gpt-oss-120b"] }), step("guardrail")],
    hypotheses: [{
      hypothesis_id: "HYP-001", candidate_root_cause: "A release left sessions open", reasons: ["Shortly after the release"],
      supporting_evidence: ["EV-001"], contradicting_evidence: [], recommended_validation: [], missing_evidence: [],
      why_chain: [], factors: [], confidence: "HIGH", confidence_points: 7, confidence_reasons: ["Change before the error"],
    }],
    evidence: [{ evidence_id: "EV-001", type: "CHANGE", source: "changes", description: "Release 4.2", citation: "CHG-2026-00001", timestamp: null, related_ids: [], service: null }],
  });
  const routes = {
    "GET /rcas/RCA-2026-00005": record, "GET /rcas/RCA-2026-00005/revisions": [record],
    "GET /problems/PRB-2026-00001": { problem: problem(1), events: [], rcas: [record] }, "GET /incidents": [],
  };

  it("folds the finished steps away (the model only in a step's details), shows the causes, and sends the draft after a confirmation", async () => {
    const calls = mockApi({ ...routes, "POST /rcas/RCA-2026-00005/submit-review": { ...record, status: "AWAITING_TECHNICAL_REVIEW" } });
    renderApp(<App />, { route: "/investigation/RCA-2026-00005" });
    expect(await screen.findByText("A release left sessions open")).toBeInTheDocument();
    expect(screen.queryByText(/gpt-oss-120b/)).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Inputs/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["inv.steps_toggle"] }));
    await userEvent.click(screen.getByRole("button", { name: /^Plan the investigation/ }));
    expect(screen.getByText(/gpt-oss-120b/)).toBeInTheDocument();
    // the evidence reads "Change: Release 4.2"; its codes are in the details behind the info button
    expect(screen.queryByText(/CHG-2026-00001/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["evidence.details"].replace("{label}", "Change: Release 4.2") }));
    expect(await screen.findByText("CHG-2026-00001")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: en["next.send"] }));
    const dialog = await screen.findByRole("dialog");
    expect(calls.some((call) => call.method === "POST")).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: en["next.send"] }));
    await waitFor(() => expect(calls.some((call) => call.method === "POST" && call.path === "/rcas/RCA-2026-00005/submit-review")).toBe(true));
    expect(await screen.findByRole("heading", { name: en["success.sent_title"] })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["success.view_history"] })).toBeInTheDocument();
  });

  it("says a run is in progress and shows no result before it ended", async () => {
    mockApi({ ...routes, "GET /rcas/RCA-2026-00005": { ...record, run_status: "RUNNING", current_step: "gather_evidence", hypotheses: [] } });
    renderApp(<App />, { route: "/investigation/RCA-2026-00005" });
    expect(await screen.findByText(en["inv.running_title"])).toBeInTheDocument();
    expect(screen.getByText("Now: Collect evidence")).toBeInTheDocument();
    expect(screen.queryByRole("tablist", { name: en["tabs.label"] })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["next.send"] })).not.toBeInTheDocument();
  });
});
