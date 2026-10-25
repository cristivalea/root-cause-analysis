import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/App";
import { en } from "@/i18n/en";
import { countByStatus, filterProblems, sortProblems } from "@/pages/problems/problemFilters";
import { draftOf, guidanceOf } from "@/pages/problems/guidance";
import { detail, incident, mockApi, problem, rca } from "./fixtures";
import { jsonResponse, renderApp, signInAs } from "./render";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
  signInAs("problem_manager", "manager");
});
afterEach(() => vi.restoreAllMocks());

const base = { tab: "all" as const, query: "", priority: "" as const, service: "", minIncidents: 1, from: "", to: "" };

describe("problem list rules", () => {
  const list = [
    problem(1, { priority: "P1", services: ["Auth Service"], title: "Login fails" }),
    problem(2, { status: "Closed" }),
    problem(3, { status: "Manual", created_at: "2026-03-01T00:00:00+00:00" }),
    problem(4, { incidents: [...problem(4).incidents, { incident_id: "INC-2026-09999", linked_at: "", linked_by: "" }] }),
  ];

  it("filters by tab, search, priority, service, incidents and dates", () => {
    expect(filterProblems(list, { ...base, tab: "Manual" }).map((item) => item.problem_id)).toEqual(["PRB-2026-00003"]);
    expect(filterProblems(list, { ...base, query: "login" })).toHaveLength(1);
    expect(filterProblems(list, { ...base, query: "prb-2026-00002" })).toHaveLength(1);
    expect(filterProblems(list, { ...base, priority: "P1" })).toHaveLength(1);
    expect(filterProblems(list, { ...base, service: "Auth Service" })).toHaveLength(1);
    expect(filterProblems(list, { ...base, minIncidents: 2 }).map((item) => item.problem_id)).toEqual(["PRB-2026-00004"]);
    expect(filterProblems(list, { ...base, from: "2026-03-01", to: "2026-03-31" }).map((item) => item.problem_id)).toEqual(["PRB-2026-00002", "PRB-2026-00003"]);
  });

  it("sorts, with the id breaking ties, and counts the tabs", () => {
    expect(sortProblems(list, "priority", "asc")[0]!.problem_id).toBe("PRB-2026-00001");
    expect(sortProblems(list, "incidents", "desc")[0]!.problem_id).toBe("PRB-2026-00004");
    expect(countByStatus(list)).toEqual({ Open: 2, "In investigation": 0, Manual: 1, Closed: 1, all: 4 });
  });
});

describe("guidance", () => {
  it("sends only what differs from the defaults, and nothing when nothing is given", () => {
    expect(guidanceOf(draftOf(null))).toBeNull();
    expect(guidanceOf({ ...draftOf(null), notes: "  check the pool ", changeDays: "14" })).toEqual({
      notes: "check the pool", instructions: null, extra_services: [], change_window_days: 14, log_hours_before: null,
    });
  });
});

describe("Problems page", () => {
  it("shows 10 open problems per page as rows that open the problem", async () => {
    const list = Array.from({ length: 12 }, (_, index) => problem(index + 1)).concat(problem(50, { status: "Closed" }));
    mockApi({ "GET /problems": list, "GET /incidents": [], "GET /services": [],
              ...Object.fromEntries(list.map((item) => [`GET /problems/${item.problem_id}`, detail(item)])) });
    renderApp(<App />, { route: "/problems" });
    expect(await screen.findByRole("tab", { name: /Open\s*12/ })).toHaveAttribute("aria-selected", "true");
    const rows = within(screen.getByRole("list", { name: en["problems.title"] })).getAllByRole("link");
    expect(rows).toHaveLength(10);
    expect(screen.getByText("1–10 of 12")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Page 2" }));
    expect(within(screen.getByRole("list", { name: en["problems.title"] })).getAllByRole("link")).toHaveLength(2);
    await userEvent.click(screen.getByRole("tab", { name: /Closed/ }));
    const closed = within(screen.getByRole("list", { name: en["problems.title"] })).getAllByRole("link");
    expect(closed).toHaveLength(1);
    await userEvent.click(screen.getByRole("tab", { name: /Open/ }));
    await userEvent.click(within(screen.getByRole("list", { name: en["problems.title"] })).getAllByRole("link")[0]!);
    expect(await screen.findByRole("heading", { level: 1, name: /Problem number/ })).toBeInTheDocument();
  });

  it("has no Proposed problems button and no checkboxes", async () => {
    mockApi({ "GET /problems": [problem(1)] });
    renderApp(<App />, { route: "/problems" });
    await screen.findByText("PRB-2026-00001");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    const main = screen.getByRole("main");
    expect(within(main).queryByRole("link", { name: en["nav.proposals"] })).not.toBeInTheDocument();
  });
});

describe("Problem page", () => {
  const open = problem(1, {
    incidents: ["INC-2026-00001", "INC-2026-00002"].map((id) => ({ incident_id: id, linked_at: "2026-10-01T10:00:00+00:00", linked_by: "manager" })),
  });
  const common = { "GET /incidents": [incident("INC-2026-00001"), incident("INC-2026-00002")], "GET /services": ["Payment API", "Auth Service"] };

  it("removes an incident only with a reason, through the API", async () => {
    const calls = mockApi({
      ...common,
      "GET /problems/PRB-2026-00001": detail(open),
      "POST /problems/PRB-2026-00001/incidents/INC-2026-00002/remove": { problem: { ...open, incidents: open.incidents.slice(0, 1) }, warnings: [] },
    });
    renderApp(<App />, { route: "/problems/PRB-2026-00001" });
    await userEvent.click(await screen.findByRole("button", { name: "Remove INC-2026-00002 from the problem" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: en["problem.remove_confirm"] }));
    expect(within(dialog).getByText(en["problem.reason_required"])).toBeInTheDocument();
    expect(calls.some((call) => call.method === "POST")).toBe(false);
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Different cause");
    await userEvent.click(within(dialog).getByRole("button", { name: en["problem.remove_confirm"] }));
    await waitFor(() => expect(calls.find((call) => call.method === "POST")?.body).toEqual({ reason: "Different cause" }));
    expect(await screen.findByText("INC-2026-00002 was removed from the problem.")).toBeInTheDocument();
  });

  it("keeps the dialog open and says why when the server refuses", async () => {
    mockApi({
      ...common,
      "GET /problems/PRB-2026-00001": detail(open),
      "POST /problems/PRB-2026-00001/close": () => jsonResponse({ detail: "The problem has an RCA in progress." }, 409),
    });
    renderApp(<App />, { route: "/problems/PRB-2026-00001" });
    await userEvent.click(await screen.findByRole("button", { name: en["problem.close_link"] }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Duplicate");
    await userEvent.click(within(dialog).getByRole("button", { name: en["problem.close"] }));
    expect(await screen.findByText("The problem has an RCA in progress.")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("starts an RCA with a request key and goes to its investigation", async () => {
    const calls = mockApi({
      ...common,
      "GET /problems/PRB-2026-00001": detail(open),
      "POST /problems/PRB-2026-00001/rcas": rca({ rca_id: "RCA-2026-00007", run_status: "RUNNING" }),
      "GET /rcas/RCA-2026-00007": rca({ rca_id: "RCA-2026-00007", run_status: "RUNNING" }),
      "GET /rcas/RCA-2026-00007/revisions": [rca({ rca_id: "RCA-2026-00007", run_status: "RUNNING" })],
    });
    renderApp(<App />, { route: "/problems/PRB-2026-00001" });
    await userEvent.click(await screen.findByRole("button", { name: en["problem.start"] }));
    await waitFor(() => expect(calls.find((call) => call.method === "POST")).toBeDefined());
    const body = calls.find((call) => call.method === "POST")!.body as { guidance: unknown; request_key: string };
    expect(body.guidance).toBeNull();
    expect(body.request_key).toMatch(/^[0-9a-f-]{36}$/);
    expect(await screen.findByText(en["inv.running_title"])).toBeInTheDocument();
  });

  it("follows the status: in investigation → open the RCA, manual → close only, closed → reopen", async () => {
    const investigating = { ...open, status: "In investigation" as const };
    mockApi({ ...common, "GET /problems/PRB-2026-00001": detail(investigating, [rca({ status: "AWAITING_TECHNICAL_REVIEW" })]) });
    const view = renderApp(<App />, { route: "/problems/PRB-2026-00001" });
    expect(await screen.findByRole("button", { name: en["problem.open_investigation"] })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["problem.start"] })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["problem.add_incident"] })).not.toBeInTheDocument();
    view.unmount();
    vi.restoreAllMocks();

    mockApi({ ...common, "GET /problems/PRB-2026-00001": detail({ ...open, status: "Manual" }) });
    const manual = renderApp(<App />, { route: "/problems/PRB-2026-00001" });
    expect(await screen.findByRole("button", { name: en["problem.close_link"] })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["problem.start"] })).not.toBeInTheDocument();
    manual.unmount();
    vi.restoreAllMocks();

    mockApi({ ...common, "GET /problems/PRB-2026-00001": detail({ ...open, status: "Closed" }) });
    renderApp(<App />, { route: "/problems/PRB-2026-00001" });
    expect(await screen.findByRole("button", { name: en["problem.reopen"] })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["problem.close_link"] })).not.toBeInTheDocument();
  });

  it("does not let the last incident be removed", async () => {
    mockApi({ ...common, "GET /problems/PRB-2026-00001": detail(problem(1)) });
    renderApp(<App />, { route: "/problems/PRB-2026-00001" });
    expect(await screen.findByRole("button", { name: en["problem.remove_last"] })).toBeDisabled();
  });
});
