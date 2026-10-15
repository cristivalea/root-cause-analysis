import type { Priority, Problem, ProblemStatus } from "@/api/types";
import { dayOf } from "@/lib/format";

export type StatusTab = ProblemStatus | "all";
export type SortKey = "problem" | "title" | "priority" | "incidents" | "created";
export type SortDirection = "asc" | "desc";

export interface ProblemFilters {
  tab: StatusTab;
  query: string;
  priority: Priority | "";
  service: string;
  minIncidents: number;
  from: string; // yyyy-mm-dd, inclusive
  to: string;
}

/** The problems a tab, the search and the filters leave, without the order. */
export function filterProblems(problems: Problem[], filters: ProblemFilters): Problem[] {
  const needle = filters.query.trim().toLowerCase();
  return problems.filter((problem) =>
    (filters.tab === "all" || problem.status === filters.tab) &&
    (!needle || problem.problem_id.toLowerCase().includes(needle) || problem.title.toLowerCase().includes(needle)) &&
    (!filters.priority || problem.priority === filters.priority) &&
    (!filters.service || problem.services.includes(filters.service)) &&
    problem.incidents.length >= filters.minIncidents &&
    (!filters.from || dayOf(problem.created_at) >= filters.from) &&
    (!filters.to || dayOf(problem.created_at) <= filters.to),
  );
}

const VALUE: Record<SortKey, (problem: Problem) => string | number> = {
  problem: (problem) => problem.problem_id,
  title: (problem) => problem.title.toLowerCase(),
  priority: (problem) => problem.priority, // P1 < P2: ascending is the most urgent first
  incidents: (problem) => problem.incidents.length,
  created: (problem) => problem.created_at,
};

export function sortProblems(problems: Problem[], key: SortKey, direction: SortDirection): Problem[] {
  const value = VALUE[key];
  const sign = direction === "asc" ? 1 : -1;
  return [...problems].sort((a, b) => {
    const left = value(a);
    const right = value(b);
    const order = left < right ? -1 : left > right ? 1 : 0;
    return order * sign || a.problem_id.localeCompare(b.problem_id);
  });
}

export function countByStatus(problems: Problem[]): Record<StatusTab, number> {
  const counts: Record<StatusTab, number> = { Open: 0, "In investigation": 0, Manual: 0, Closed: 0, all: problems.length };
  for (const problem of problems) counts[problem.status] += 1;
  return counts;
}
