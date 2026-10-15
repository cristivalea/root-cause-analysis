import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { en, type MessageKey } from "./en";
import { ro } from "./ro";

export type Language = "en" | "ro";
export type Translate = (key: MessageKey, values?: Record<string, string | number>) => string;

const CATALOGUES: Record<Language, Record<MessageKey, string>> = { en, ro };
const STORAGE_KEY = "rca.language";

function savedLanguage(): Language {
  try {
    return localStorage.getItem(STORAGE_KEY) === "ro" ? "ro" : "en";
  } catch {
    return "en";
  }
}

/** "{count} items" with {count: 3} → "3 items". An unknown placeholder is left as it is. */
export function format(template: string, values?: Record<string, string | number>): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (name in values ? String(values[name]) : match));
}

interface I18n {
  language: Language;
  setLanguage: (language: Language) => void;
  t: Translate;
}

const I18nContext = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(savedLanguage);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // private mode: the choice lasts for this visit only
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const t = useCallback<Translate>((key, values) => format(CATALOGUES[language][key] ?? en[key], values), [language]);
  const value = useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n is used outside I18nProvider");
  return context;
}
