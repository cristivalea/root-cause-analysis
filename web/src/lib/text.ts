/** The lines of a text as a list, each said once: "- " or "* " in front and repeated lines are dropped.
 * Requests saved before 2026-10-15 hold the expert's lines twice (as the comment and as the checks). */
export function uniqueLines(...texts: (string | null | undefined)[]): string[] {
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const text of texts) {
    for (const raw of (text ?? "").split("\n")) {
      const line = raw.replace(/^[-*\s]+/, "").trim();
      if (line && !seen.has(line.toLowerCase())) {
        seen.add(line.toLowerCase());
        lines.push(line);
      }
    }
  }
  return lines;
}

/** A value of a step's details as words, never as JSON: an object becomes "key: value · key: value". */
export function readable(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(readable).join(", ");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== null && item !== undefined && item !== "")
      .map(([key, item]) => `${key.replace(/_/g, " ")}: ${readable(item)}`)
      .join(" · ");
  }
  return String(value);
}
