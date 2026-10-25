import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/App";
import { en } from "@/i18n/en";
import { ro } from "@/i18n/ro";
import { format } from "@/i18n/I18nProvider";
import { allowedFor } from "@/lib/navigation";
import { pageItems } from "@/components/ui/Pagination";
import { PillTabs } from "@/components/ui/PillTabs";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { jsonResponse, renderApp, signInAs } from "./render";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  // Radix measures elements; jsdom has no ResizeObserver
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
});
afterEach(() => vi.restoreAllMocks());

describe("i18n", () => {
  it("has a Romanian text for every English key, and no other", () => {
    expect(Object.keys(ro).sort()).toEqual(Object.keys(en).sort());
    for (const [key, value] of Object.entries(ro)) expect(value, key).not.toBe("");
  });

  it("keeps the same placeholders in both languages", () => {
    const names = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
    for (const key of Object.keys(en) as (keyof typeof en)[]) expect(names(ro[key]), key).toEqual(names(en[key]));
  });

  it("fills placeholders and leaves unknown ones", () => {
    expect(format("{from}–{to} of {total}", { from: 1, to: 10, total: 37 })).toBe("1–10 of 37");
    expect(format("Hello {name}", {})).toBe("Hello {name}");
  });
});

describe("navigation rules", () => {
  it("keeps each role on its own pages", () => {
    expect(allowedFor("problem_manager", "/problems/PRB-2026-00001")).toBe(true);
    expect(allowedFor("problem_manager", "/review")).toBe(false);
    expect(allowedFor("technical_expert", "/review/RCA-2026-00001")).toBe(true);
    expect(allowedFor("technical_expert", "/problems")).toBe(false);
    expect(allowedFor("technical_expert", "/")).toBe(true);
    // not in the menu, but still the Problem Manager's page; the guide belongs to both roles
    expect(allowedFor("problem_manager", "/investigation/RCA-2026-00001")).toBe(true);
    expect(allowedFor("technical_expert", "/investigation/RCA-2026-00001")).toBe(false);
    expect(allowedFor("technical_expert", "/how-it-works")).toBe(true);
  });

  it("shows the first, the last and the neighbours of the current page", () => {
    expect(pageItems(1, 4)).toEqual([1, 2, 3, 4]);
    expect(pageItems(5, 10)).toEqual([1, "gap", 4, 5, 6, "gap", 10]);
    expect(pageItems(1, 10)).toEqual([1, 2, "gap", 10]);
  });
});

describe("login", () => {
  it("asks for both fields before calling the server", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    renderApp(<App />, { route: "/login" });
    await userEvent.click(screen.getByRole("button", { name: en["login.submit"] }));
    expect(screen.getByText(en["login.required_username"])).toBeInTheDocument();
    expect(screen.getByText(en["login.required_password"])).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("says the credentials are wrong on a 401 and keeps the username", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "Utilizator sau parolă incorectă." }, 401));
    renderApp(<App />, { route: "/login" });
    await userEvent.type(screen.getByLabelText(en["login.username"]), "someone");
    await userEvent.type(screen.getByLabelText(en["login.password"]), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: en["login.submit"] }));
    expect(await screen.findByText(en["login.wrong"])).toBeInTheDocument();
    expect(screen.getByLabelText(en["login.username"])).toHaveValue("someone");
    expect(screen.getByLabelText(en["login.password"])).toHaveValue("");
  });

  it("signs in and shows the menu of the role the server returned", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ access_token: "t", token_type: "bearer", username: "expert", role: "technical_expert" }),
    );
    renderApp(<App />, { route: "/login" });
    await userEvent.type(screen.getByLabelText(en["login.username"]), "expert");
    await userEvent.type(screen.getByLabelText(en["login.password"]), "a-password");
    await userEvent.click(screen.getByRole("button", { name: en["login.submit"] }));
    const menu = (await screen.findAllByRole("navigation", { name: en["nav.label"] }))[0]!;
    expect(within(menu).getByRole("link", { name: en["nav.review"] })).toBeInTheDocument();
    expect(within(menu).queryByRole("link", { name: en["nav.problems"] })).not.toBeInTheDocument();
    expect(sessionStorage.getItem("rca.token")).toBe("t");
  });

  it("switches the login page to Romanian", async () => {
    renderApp(<App />, { route: "/login" });
    await userEvent.click(screen.getByRole("radio", { name: "Română" }));
    expect(screen.getByRole("heading", { name: ro["login.welcome"] })).toBeInTheDocument();
    expect(localStorage.getItem("rca.language")).toBe("ro");
  });
});

describe("shell and guards", () => {
  it("sends a visitor without a session to the login page", () => {
    renderApp(<App />, { route: "/problems" });
    expect(screen.getByRole("heading", { name: en["login.welcome"] })).toBeInTheDocument();
  });

  it("shows the Problem Manager only the Problem Manager pages", () => {
    signInAs("problem_manager", "manager");
    renderApp(<App />, { route: "/" });
    const menu = screen.getAllByRole("navigation", { name: en["nav.label"] })[0]!;
    const links = within(menu).getAllByRole("link").map((link) => link.textContent);
    expect(links).toEqual([en["nav.home"], en["nav.problems"], en["nav.proposals"], en["nav.history"], en["nav.kpis"]]);
  });

  it("takes the expert home from a Problem Manager page", async () => {
    signInAs("technical_expert");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
    renderApp(<App />, { route: "/problems" });
    expect(await screen.findByRole("heading", { level: 1, name: "Hello, tester" })).toBeInTheDocument();
  });

  it("keeps Home to the actions and opens how the application works from it", async () => {
    signInAs("problem_manager", "manager");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
    renderApp(<App />, { route: "/" });
    expect(screen.queryByRole("heading", { name: en["home.how_title"] })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: en["guide.link"] }));
    expect(await screen.findByRole("heading", { level: 1, name: en["guide.title"] })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: en["home.how_title"] })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: en["home.claims_title"] })).toBeInTheDocument();
  });

  it("logs out from the user menu", async () => {
    signInAs("problem_manager", "manager");
    renderApp(<App />, { route: "/" });
    await userEvent.click(screen.getByRole("button", { name: en["user.menu"] }));
    await userEvent.click(await screen.findByRole("menuitem", { name: en["user.sign_out"] }));
    await waitFor(() => expect(screen.getByRole("heading", { name: en["login.welcome"] })).toBeInTheDocument());
    expect(sessionStorage.getItem("rca.token")).toBeNull();
  });
});

describe("components", () => {
  it("moves between pill tabs with the arrow keys", async () => {
    function Tabs() {
      const [value, setValue] = useState<"a" | "b">("a");
      return <PillTabs label="Status" value={value} onChange={setValue}
                       tabs={[{ value: "a", label: "Open", count: 3 }, { value: "b", label: "Closed", count: 1 }]}>{value}</PillTabs>;
    }
    renderApp(<Tabs />);
    const open = screen.getByRole("tab", { name: /Open/ });
    expect(open).toHaveAttribute("aria-selected", "true");
    open.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /Closed/ })).toHaveAttribute("aria-selected", "true");
  });

  it("does not confirm without the required reason", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    renderApp(
      <ConfirmDialog open onOpenChange={() => {}} title="Close the problem?" confirmLabel="Close problem" onConfirm={onConfirm}
                     reason={{ label: "Reason", required: true, requiredMessage: "Give a reason." }} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Close problem" }));
    expect(screen.getByText("Give a reason.")).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/Reason/), "Duplicate of another problem");
    await userEvent.click(screen.getByRole("button", { name: "Close problem" }));
    expect(onConfirm).toHaveBeenCalledWith("Duplicate of another problem");
  });
});
