import type { Language, Translate } from "@/i18n/I18nProvider";

const LOCALES: Record<Language, string> = { en: "en-GB", ro: "ro-RO" };

function parse(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string | null | undefined, language: Language): string {
  const date = parse(value);
  return date ? date.toLocaleDateString(LOCALES[language], { day: "numeric", month: "short", year: "numeric" }) : "—";
}

export function formatDateTime(value: string | null | undefined, language: Language): string {
  const date = parse(value);
  return date
    ? date.toLocaleString(LOCALES[language], { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : "—";
}

export function formatMinutes(minutes: number | null | undefined, t: Translate): string {
  if (minutes === null || minutes === undefined) return "—";
  if (minutes < 60) return t("format.minutes", { count: minutes });
  return t("format.hours_minutes", { hours: Math.floor(minutes / 60), minutes: minutes % 60 });
}

export function formatSeconds(seconds: number | null | undefined, t: Translate): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 90) return t("format.seconds", { count: Math.round(seconds) });
  return formatMinutes(Math.round(seconds / 60), t);
}

export function formatNumber(value: number | null | undefined, language: Language): string {
  return value === null || value === undefined ? "—" : value.toLocaleString(LOCALES[language]);
}

/** The date part (yyyy-mm-dd) of an ISO timestamp, for comparing with a date input. */
export const dayOf = (value: string) => value.slice(0, 10);
