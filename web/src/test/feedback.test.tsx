import { beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { en } from "@/i18n/en";
import { readable, uniqueLines } from "@/lib/text";
import { StepDetails } from "@/components/rca/StepDetails";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { renderApp } from "./render";

beforeEach(() => {
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
});

describe("text helpers", () => {
  it("says each line of a request once, whatever the bullets", () => {
    const saved = "check the secrets\ncheck the DNS changes\n- check the secrets\n- check the DNS changes";
    expect(uniqueLines(saved)).toEqual(["check the secrets", "check the DNS changes"]);
    expect(uniqueLines("one line", "one line")).toEqual(["one line"]);
  });

  it("turns objects into words, never JSON", () => {
    expect(readable({ id: "RCA-1", reason: "Same symptoms" })).toBe("id: RCA-1 · reason: Same symptoms");
    expect(readable(["a", 2, true])).toBe("a, 2, true");
  });
});

describe("step details", () => {
  const view = (name: string, details: Record<string, unknown>) => ({
    name, state: "done" as const, runs: 1,
    step: { name, summary: `${name} done`, started_at: "2026-10-14T10:00:00Z", finished_at: "2026-10-14T10:00:05Z", details },
  });

  it("shows the past records kept and set aside as words, with their reason", () => {
    const { container } = renderApp(<StepDetails plan={null} view={view("historical_review", {
      kept: [{ id: "RCA-2025-00114", reason: "Same Payment API symptoms", came_back_after: true }],
      dropped: [{ id: "RCA-2025-00042", reason: "Another service" }],
      findings: [{ citation: "RCA-2025-00114", similarities: ["HTTP 500"], differences: ["Older release"] }],
    })} />);
    expect(screen.getAllByText("RCA-2025-00114")).toHaveLength(2); // kept, and in the findings
    expect(screen.getByText("Same Payment API symptoms")).toBeInTheDocument();
    expect(screen.getByText(en["step.came_back"])).toBeInTheDocument();
    expect(screen.getByText("Another service")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/[{}"]/);
  });

  it("says when a step took the expert's request into account, and shows the request once", () => {
    renderApp(<StepDetails plan={null} view={view("build_context", {
      input: { expert_request: true, guidance: false },
      given_text: { "expert request": "check the secrets\n- check the secrets" },
    })} />);
    expect(screen.getByText(en["step.read.expert_request"])).toBeInTheDocument();
    expect(screen.getAllByText("check the secrets")).toHaveLength(1);
  });
});

describe("confirmation without a reason", () => {
  it("has no empty body between the question and the buttons", () => {
    renderApp(<ConfirmDialog open onOpenChange={() => {}} title="Send it?" description="The expert reviews it." confirmLabel="Send" onConfirm={async () => {}} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.querySelectorAll(".overflow-y-auto")).toHaveLength(0);
    expect(dialog.querySelector(".border-b, .border-t")).toBeNull();
  });
});
