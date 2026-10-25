import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/App";
import { en } from "@/i18n/en";
import type { KpiReport } from "@/api/types";
import { mockApi } from "./fixtures";
import { renderApp, signInAs } from "./render";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
  signInAs("problem_manager");
});
afterEach(() => vi.restoreAllMocks());

const report = (change: Partial<KpiReport> = {}): KpiReport => ({
  period: { from: null, to: null },
  overview: { problems: { Open: 11, "In investigation": 0, Manual: 1, Closed: 27 }, awaiting_review: 0, rcas_started: 9,
              rcas_running: 0, problems_closed: 27, median_hours_to_decision: 0.15, decided_count: 8 },
  kpi1_interactions: { finished: 8, average_interactions: 4.38, reduction_percent: 60.2, happy_path: 7, with_more_steps: 1,
                       manual_interactions: 11, design_interactions: 4, design_reduction_percent: 63.64 },
  kpi2_autonomy: { runs: 10, autonomous: 9, failed: 0, refused_by_checks: 1, rate_percent: 90, design_automated: 5, design_stages: 8, design_percent: 62.5 },
  kpi3_accuracy: { decided: 8, top1: 5, topk: 5, top1_percent: 62.5, topk_percent: 62.5 },
  kpi4_calibration: { decisions: 9, ordered: false, levels: [
    { level: "HIGH", decisions: 4, approved: 2, approved_percent: 50 },
    { level: "MEDIUM", decisions: 5, approved: 3, approved_percent: 60 },
    { level: "LOW", decisions: 0, approved: 0, approved_percent: null }] },
  weeks: [{ week: "2026-10-12", started: 8, validated: 4, rejected: 3 }],
  benchmark: {
    accuracy: { status: "not_measured", timestamp: null, agent_model: null, judge_model: null, selected: null, evaluated: null, values: {}, excluded: [] },
    calibration: { status: "outdated", timestamp: "2026-10-06T13:02:12Z", agent_model: null, judge_model: null, selected: null, evaluated: null, values: {}, excluded: [] },
  },
  ...change,
});

/** The charts and the test on known cases are folded under "See the details" on every card. */
async function openDetails() {
  for (const button of screen.getAllByRole("button", { name: en["kpis.details"] })) await userEvent.click(button);
}

describe("KPI page", () => {
  it("shows the four KPIs with their basis, their targets, and no benchmark number without a valid report", async () => {
    mockApi({ "GET /kpis": report() });
    renderApp(<App />, { route: "/kpis" });
    expect(await screen.findByText("60.2%")).toBeInTheDocument();
    expect(screen.queryByText(/KPI 1/)).not.toBeInTheDocument();
    await openDetails();
    expect(screen.getByText("63.64%")).toBeInTheDocument(); // the teammate's calculation, as written
    expect(screen.getByText("90%")).toBeInTheDocument();
    expect(screen.getAllByText("62.5%").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(en["kpi4.ordered_no"])).toBeInTheDocument();
    expect(screen.getByText(en["kpis.bench.not_measured"])).toBeInTheDocument();
    expect(screen.getByText(/is out of date and is not shown/)).toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
    expect(screen.getAllByText(en["kpis.few"]).length).toBeGreaterThan(0); // 8–10 cases: a first signal
    expect(screen.getByText("9 min")).toBeInTheDocument();
  });

  it("shows a measured exam with its date and the cases counted, without the model or the excluded IDs", async () => {
    mockApi({ "GET /kpis": report({ benchmark: { ...report().benchmark, accuracy: {
      status: "measured", timestamp: "2026-10-16T09:00:00Z", agent_model: "openai/gpt-oss-120b", judge_model: "llama-3.3-70b-versatile",
      selected: 13, evaluated: 12, values: { top1_percent: 66.67, topk_percent: 91.67 }, excluded: ["INC-2026-00110"] } } }) });
    renderApp(<App />, { route: "/kpis" });
    await screen.findByText("60.2%");
    await openDetails();
    expect(screen.getByText("91.67%")).toBeInTheDocument();
    expect(screen.getByText(/12 of 13 cases counted/)).toBeInTheDocument();
    expect(screen.queryByText(/gpt-oss-120b/)).not.toBeInTheDocument();
    expect(screen.queryByText(/INC-2026-00110/)).not.toBeInTheDocument();
  });

  it("asks the server for the period chosen", async () => {
    const calls = mockApi({ "GET /kpis": report() });
    const routes = (path: string) => calls.some((call) => call.path.startsWith(path));
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = new URL(String(input), "http://localhost");
      calls.push({ method: "GET", path: url.pathname.replace("/api/v1", "") + url.search, body: undefined });
      return new Response(JSON.stringify(report()), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    renderApp(<App />, { route: "/kpis" });
    await screen.findByText("60.2%");
    await userEvent.click(screen.getByRole("tab", { name: en["kpis.period.30"] }));
    await waitFor(() => expect(routes("/kpis?date_from=")).toBe(true));
    const from = calls.find((call) => call.path.startsWith("/kpis?date_from="))!.path.split("=")[1]!;
    const expected = new Date();
    expected.setDate(expected.getDate() - 29);
    expect(from).toBe(`${expected.getFullYear()}-${String(expected.getMonth() + 1).padStart(2, "0")}-${String(expected.getDate()).padStart(2, "0")}`);
  });

  it("does not draw a bar for a confidence level without decisions", async () => {
    mockApi({ "GET /kpis": report() });
    renderApp(<App />, { route: "/kpis" });
    await screen.findByText("60.2%");
    await openDetails();
    expect(screen.getAllByText("50% (2/4)")).toHaveLength(2); // on the chart, and in the table for screen readers
    const low = screen.getByText(en["confidence.LOW"], { selector: "span" }).parentElement!;
    expect(low.querySelectorAll("[tabindex]")).toHaveLength(0);
  });
});
