import { clsx } from "clsx";
import { useI18n, type Language } from "@/i18n/I18nProvider";

const LANGUAGES: Language[] = ["en", "ro"];

/** EN | RO as a two-option switch; the choice is remembered in this browser. */
export function LanguageSwitch({ tone = "light", className }: { tone?: "light" | "dark"; className?: string }) {
  const { language, setLanguage, t } = useI18n();
  return (
    <div role="radiogroup" aria-label={t("lang.label")}
         className={clsx("inline-flex rounded-full p-0.5 text-xs font-semibold",
           tone === "light" ? "border border-line bg-surface" : "bg-white/10", className)}>
      {LANGUAGES.map((item) => {
        const active = item === language;
        return (
          <button
            key={item}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={t(`lang.${item}`)}
            onClick={() => setLanguage(item)}
            className={clsx(
              "h-7 rounded-full px-3 uppercase transition-colors",
              active
                ? tone === "light" ? "bg-brand-600 text-white" : "bg-white text-brand-950"
                : tone === "light" ? "text-muted hover:text-ink" : "text-white/70 hover:text-white",
            )}
          >
            {item}
          </button>
        );
      })}
    </div>
  );
}
