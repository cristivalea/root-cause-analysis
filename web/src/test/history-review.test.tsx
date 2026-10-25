import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/App";
import { en } from "@/i18n/en";
import type { Hypothesis, RCASummary } from "@/api/types";
import { filterHistory } from "@/pages/history/historyFilters";
import { requestedChecks } from "@/pages/review/ReviewDecisions";
import { mockApi, problem, rca } from "./fixtures";
import { renderApp, signInAs } from "./render";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
});
afterEach(() => vi.restoreAllMocks());

const summary = (id: string, change: Partial<RCASummary> = {}): RCASummary => ({
  rca_id: id, problem_id: "PRB-2026-00001", title: "Payments fail", status: "VALIDATED", created_at: "2026-10-01T10:00:00Z",
  created_by: "manager", updated_at: "2026-10-02T10:00:00Z", revisions: 1, review_rounds: 1, sent_to_expert: true,
  latest_revision_id: `${id}-R1`, ...change,
});

const hypothesis = (id: string, cause: string): Hypothesis => ({
  hypothesis_id: id, candidate_root_cause: cause, reasons: [], supporting_evidence: [], contradicting_evidence: [],
  recommended_validation: [], missing_evidence: [], why_chain: [], factors: [], confidence: "MEDIUM", confidence_points: 4, confidence_reasons: [],
});

describe("history filters", () => {
  const list = [summary("RCA-2026-00001"), summary("RCA-2026-00002", { status: "REJECTED", problem_id: "PRB-2026-00002", title: "Login slow", created_at: "2026-08-01T00:00:00Z" })];
  const revisions = new Map([["RCA-2026-00001", [rca({ rca_id: "RCA-2026-00001", incident_id: "INC-2026-00777" })]]]);
  const services = new Map([["PRB-2026-00001", ["Payment API"]], ["PRB-2026-00002", ["Auth Service"]]]);
  const base = { query: "", status: "" as const, service: "", from: "", to: "" };

  it("searches revision and incident ids, and filters by status, service and start date", () => {
    expect(filterHistory(list, revisions, services, { ...base, query: "inc-2026-00777" }).map((item) => item.rca_id)).toEqual(["RCA-2026-00001"]);
    expect(filterHistory(list, revisions, services, { ...base, query: "RCA-2026-00001-R1" })).toHaveLength(1);
    expect(filterHistory(list, revisions, services, { ...base, status: "REJECTED" }).map((item) => item.rca_id)).toEqual(["RCA-2026-00002"]);
    expect(filterHistory(list, revisions, services, { ...base, service: "Payment API" }).map((item) => item.rca_id)).toEqual(["RCA-2026-00001"]);
    expect(filterHistory(list, revisions, services, { ...base, to: "2026-09-01" }).map((item) => item.rca_id)).toEqual(["RCA-2026-00002"]);
  });
});

describe("RCA history pages", () => {
  it("lists the RCAs with one Open case each, and the case shows every revision with one Open investigation", async () => {
    signInAs("problem_manager");
    const first = rca({ rca_id: "RCA-2026-00001", revision: 1, status: "REQUEST_MORE_DETAILS",
      review: { reviewer: "expert", decision: "REQUEST_MORE_DETAILS", hypothesis_id: null, comment: "Check the driver", decided_at: "2026-10-02T10:00:00Z", requested_checks: [], guidance: null } });
    const second = rca({ rca_id: "RCA-2026-00001", revision: 2, status: "DRAFT" });
    mockApi({
      "GET /rcas/summaries": [summary("RCA-2026-00001", { status: "DRAFT", revisions: 2 })], "GET /cases": [[first, second]], "GET /problems": [problem(1)],
      "GET /rcas/RCA-2026-00001/history": { rca: summary("RCA-2026-00001", { status: "DRAFT", revisions: 2 }), history: [] },
      "GET /rcas/RCA-2026-00001/revisions": [first, second],
    });
    renderApp(<App />, { route: "/history" });
    await userEvent.click(await screen.findByRole("link", { name: "Payments fail" })); // the title opens the case, and covers the whole card
    expect(await screen.findByText("Version 2")).toBeInTheDocument();
    expect(screen.getByText("Version 1")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: en["case.open_investigation"] }).map((link) => link.getAttribute("href")))
      .toEqual(["/investigation/RCA-2026-00001-R2", "/investigation/RCA-2026-00001-R1"]);
    expect(screen.queryByText(/Show analysis/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Problem PRB-2026-00001/ })).toHaveAttribute("href", "/problems/PRB-2026-00001");
  });
});

describe("Home of the Problem Manager", () => {
  it("lists what waits for a step from the Problem Manager, each opening its investigation", async () => {
    signInAs("problem_manager");
    mockApi({
      "GET /problems": [problem(1)], "GET /rcas/summaries": [summary("RCA-2026-00004", { status: "DRAFT", title: "Ready one" }),
        summary("RCA-2026-00005", { status: "FAILED", title: "Stopped one" })],
      "GET /rcas?status=DRAFT": [rca({ rca_id: "RCA-2026-00004" }), rca({ rca_id: "RCA-2026-00006", run_status: "RUNNING" })],
      "GET /rcas?status=REQUEST_MORE_DETAILS": [], "GET /rcas?status=FAILED": [rca({ rca_id: "RCA-2026-00005", status: "FAILED", run_status: "FAILED" })],
      "GET /rcas?status=AWAITING_TECHNICAL_REVIEW": [rca({ rca_id: "RCA-2026-00007", status: "AWAITING_TECHNICAL_REVIEW" })],
    });
    renderApp(<App />, { route: "/" });
    expect(await screen.findByRole("link", { name: /Ready one/ })).toHaveAttribute("href", "/investigation/RCA-2026-00004");
    expect(screen.getByRole("link", { name: /Stopped one/ })).toHaveAttribute("href", "/investigation/RCA-2026-00005");
    expect(screen.queryByRole("link", { name: /RCA-2026-00006/ })).not.toBeInTheDocument(); // running: nothing to do yet
    expect(screen.getByText("Running now: 1 · With the expert: 1")).toBeInTheDocument();
    expect(screen.getByText(en["home.todo.none"])).toBeInTheDocument(); // no request from the expert
  });
});

describe("Technical review", () => {
  const waiting = rca({ rca_id: "RCA-2026-00003", status: "AWAITING_TECHNICAL_REVIEW", run_status: "COMPLETED",
    hypotheses: [hypothesis("HYP-001", "A release left sessions open"), hypothesis("HYP-002", "Traffic spike")] });
  const routes = {
    "GET /rcas?status=AWAITING_TECHNICAL_REVIEW": [waiting], "GET /rcas/summaries": [summary("RCA-2026-00003", { status: "AWAITING_TECHNICAL_REVIEW" })],
    "GET /rcas/RCA-2026-00003": waiting, "GET /rcas/RCA-2026-00003-R1/diagram": null,
  };

  it("turns a request of several lines into several checks", () => {
    expect(requestedChecks("check the driver")).toBeNull();
    expect(requestedChecks("- check the driver\n* check the pool size\n")).toEqual(["check the driver", "check the pool size"]);
  });

  it("lists what waits and opens the review", async () => {
    signInAs("technical_expert");
    mockApi(routes);
    renderApp(<App />, { route: "/review" });
    await userEvent.click(await screen.findByRole("link", { name: "Payments fail" }));
    expect(await screen.findByRole("heading", { name: en["review.decide_title"] })).toBeInTheDocument();
  });

  it("approves the chosen cause with an optional comment", async () => {
    signInAs("technical_expert");
    const calls = mockApi({ ...routes, "POST /rcas/RCA-2026-00003/review": { ...waiting, status: "VALIDATED" } });
    renderApp(<App />, { route: "/review/RCA-2026-00003" });
    await userEvent.click(await screen.findByRole("button", { name: en["review.approve"] }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("radio", { name: /Traffic spike/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: en["review.approve"] }));
    await waitFor(() => expect(calls.find((call) => call.method === "POST")?.body).toEqual({ decision: "APPROVE", comment: "", hypothesis_id: "HYP-002" }));
  });

  it("asks for more details only with a request, and rejects only with a reason", async () => {
    signInAs("technical_expert");
    const calls = mockApi({ ...routes, "POST /rcas/RCA-2026-00003/review": { ...waiting, status: "REQUEST_MORE_DETAILS" } });
    renderApp(<App />, { route: "/review/RCA-2026-00003" });
    await userEvent.click(await screen.findByRole("button", { name: en["review.request"] }));
    let dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: en["review.request"] }));
    expect(within(dialog).getByText(en["review.request_required"])).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText(/What should be verified/), "Check the driver");
    await userEvent.click(within(dialog).getByRole("button", { name: en["review.request"] }));
    await waitFor(() => expect(calls.find((call) => call.method === "POST")?.body).toEqual({
      decision: "REQUEST_MORE_DETAILS", comment: "Check the driver", requested_checks: null, guidance: null,
    }));

    expect(await screen.findByRole("heading", { name: en["success.requested_title"] })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["success.view_details"] }));

    calls.length = 0;
    await userEvent.click(screen.getByRole("button", { name: en["review.reject"] }));
    dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: en["review.reject"] }));
    expect(within(dialog).getByText(en["problem.reason_required"])).toBeInTheDocument();
    expect(calls.some((call) => call.method === "POST")).toBe(false);
  });

  it("shows the outcome instead of the decisions once decided", async () => {
    signInAs("technical_expert");
    mockApi({ ...routes, "GET /rcas/RCA-2026-00003": { ...waiting, status: "REJECTED",
      review: { reviewer: "expert", decision: "REJECT", hypothesis_id: null, comment: "Not enough evidence", decided_at: "2026-10-02T10:00:00Z", requested_checks: [], guidance: null } } });
    renderApp(<App />, { route: "/review/RCA-2026-00003" });
    expect(await screen.findByText(en["review.outcome.REJECTED"])).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["review.approve"] })).not.toBeInTheDocument();
    expect(within(screen.getByRole("main")).getByRole("link", { name: en["review.back"] })).toHaveAttribute("href", "/review?tab=checked");
  });

  it("lists the analyses already checked in their own tab, to open read-only", async () => {
    signInAs("technical_expert");
    mockApi({ ...routes, "GET /rcas/summaries": [
      summary("RCA-2026-00003", { status: "AWAITING_TECHNICAL_REVIEW", title: "Still waiting" }),
      summary("RCA-2026-00004", { status: "VALIDATED", title: "Login slow", review_rounds: 2 }),
      summary("RCA-2026-00005", { status: "DRAFT", title: "Never checked", review_rounds: 0 }),
    ] });
    renderApp(<App />, { route: "/review" });
    await userEvent.click(await screen.findByRole("tab", { name: new RegExp(en["queue.tab.checked"]) }));
    expect(await screen.findByText("Login slow")).toBeInTheDocument();
    expect(screen.queryByText("Never checked")).not.toBeInTheDocument();
    expect(screen.queryByText("Still waiting")).not.toBeInTheDocument();
    expect(screen.getByText("2 of 3 expert decisions")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Login slow" })).toHaveAttribute("href", "/review/RCA-2026-00004");
  });
});
