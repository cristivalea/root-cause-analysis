import type { Evidence } from "@/api/types";

const cut = (text: string, max: number) => {
  const clean = text.replace(/\s+/g, " ").trim().replace(/[.:;,]$/, "");
  return clean.length > max ? `${clean.slice(0, max - 1).trimEnd()}…` : clean;
};

/** A short description of a piece of evidence, from the sentence the code wrote for it (rca/evidence.py and
 * rca/pipeline.py build each type with a fixed pattern): the error type of a log group, the title of a change
 * or an incident, the link of a CMDB item, the summary of a past RCA. Anything else: the start of the text. */
export function evidenceSummary(item: Evidence, max = 70): string {
  const text = item.description ?? "";
  let found: string | null = null;
  switch (item.type) {
    case "LOG": {
      const log = /(?:On ([^,]+), a dependency: )?(\d+) \w+ log line\(s\) of type (\S+)/.exec(text);
      if (log) found = `${log[3]} (${log[2]}×)${log[1] ? ` · ${log[1]}` : ""}`;
      break;
    }
    case "CHANGE":
      found = /^(.+?) on CI-[\w-]+:/.exec(text)?.[1] ?? null;
      break;
    case "CMDB": {
      const link = /^(.+?) \(CI-[\w-]+\) \w+ (.+?) \(CI-/.exec(text);
      if (link) found = `${link[1]} → ${link[2]}`;
      break;
    }
    case "INCIDENT":
      found = /UTC: (.+?)\. /.exec(text)?.[1] ?? null;
      break;
    case "HISTORICAL_INCIDENT":
      found = /detected \d{4}-\d{2}-\d{2}: (.+?)\. /.exec(text)?.[1] ?? null;
      break;
    case "HISTORICAL_RCA":
      found = /Summary: (.+?)(?:\. |$)/.exec(text)?.[1] ?? /^.+?\d{4}-\d{2}-\d{2}\. (.+?)(?:\. |$)/.exec(text)?.[1] ?? null;
      break;
  }
  return cut(found ?? text, max);
}
