import { BarChart3, ClipboardCheck, FolderSearch, History, Home, Lightbulb, type LucideIcon } from "lucide-react";
import type { Role } from "@/api/types";
import type { MessageKey } from "@/i18n/en";

export interface NavItem {
  to: string;
  label: MessageKey;
  icon: LucideIcon;
}

/** The pages of each role, in the order of the menu. The signed-in user's role decides which list is shown;
 * the backend refuses the other role's data anyway. */
export const NAVIGATION: Record<Role, NavItem[]> = {
  problem_manager: [
    { to: "/", label: "nav.home", icon: Home },
    { to: "/problems", label: "nav.problems", icon: FolderSearch },
    { to: "/proposals", label: "nav.proposals", icon: Lightbulb },
    { to: "/history", label: "nav.history", icon: History },
    { to: "/kpis", label: "nav.kpis", icon: BarChart3 },
  ],
  technical_expert: [
    { to: "/", label: "nav.home", icon: Home },
    { to: "/review", label: "nav.review", icon: ClipboardCheck },
  ],
};

/** The pages of a role that are not in its menu: an investigation is opened from its problem or the history. */
const UNLISTED: Record<Role, string[]> = { problem_manager: ["/investigation"], technical_expert: [] };

const pathsOf = (role: Role) => [...NAVIGATION[role].map((item) => item.to).filter((to) => to !== "/"), ...UNLISTED[role]];

/** Whether a path belongs to the pages of a role (home and unknown pages belong to both). */
export function allowedFor(role: Role, pathname: string): boolean {
  const other: Role = role === "problem_manager" ? "technical_expert" : "problem_manager";
  const own = pathsOf(role).some((to) => pathname.startsWith(to));
  const foreign = pathsOf(other).some((to) => pathname.startsWith(to));
  return own || !foreign;
}
