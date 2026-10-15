import type { InvestigationGuidance } from "@/api/types";

/** The defaults of rca/context.py when nothing is given: a value equal to them is sent as "not given". */
export const DEFAULT_CHANGE_DAYS = 7;
export const DEFAULT_LOG_HOURS = 2;
export const CHANGE_DAYS = { min: 7, max: 90 };
export const LOG_HOURS = { min: 2, max: 168 };

export interface GuidanceDraft {
  notes: string;
  instructions: string;
  services: string[];
  changeDays: string;
  logHours: string;
}

export function draftOf(guidance: InvestigationGuidance | null | undefined): GuidanceDraft {
  return {
    notes: guidance?.notes ?? "",
    instructions: guidance?.instructions ?? "",
    services: guidance?.extra_services ?? [],
    changeDays: String(guidance?.change_window_days ?? DEFAULT_CHANGE_DAYS),
    logHours: String(guidance?.log_hours_before ?? DEFAULT_LOG_HOURS),
  };
}

const inRange = (value: string, range: { min: number; max: number }) => {
  const number = Number(value);
  return Number.isInteger(number) && number >= range.min && number <= range.max;
};

export function draftErrors(draft: GuidanceDraft) {
  return { changeDays: !inRange(draft.changeDays, CHANGE_DAYS), logHours: !inRange(draft.logHours, LOG_HOURS) };
}

/** The guidance for the API (models.InvestigationGuidance), or null when nothing differs from the defaults:
 * only what was filled in is sent, so the rules of the investigation apply to the rest (as the Streamlit form). */
export function guidanceOf(draft: GuidanceDraft): InvestigationGuidance | null {
  const changeDays = Number(draft.changeDays);
  const logHours = Number(draft.logHours);
  const guidance: InvestigationGuidance = {
    notes: draft.notes.trim() || null,
    instructions: draft.instructions.trim() || null,
    extra_services: draft.services,
    change_window_days: changeDays !== DEFAULT_CHANGE_DAYS ? changeDays : null,
    log_hours_before: logHours !== DEFAULT_LOG_HOURS ? logHours : null,
  };
  const given = guidance.notes || guidance.instructions || guidance.extra_services.length || guidance.change_window_days || guidance.log_hours_before;
  return given ? guidance : null;
}

export const sameGuidance = (a: InvestigationGuidance | null, b: InvestigationGuidance | null | undefined) =>
  JSON.stringify(a) === JSON.stringify(guidanceOf(draftOf(b ?? null)));
