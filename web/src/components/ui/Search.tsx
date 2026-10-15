import { useEffect, useState, type ReactNode } from "react";
import * as Popover from "@radix-ui/react-popover";
import { clsx } from "clsx";
import { Search, SlidersHorizontal, X } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import { Button } from "./Button";

/** A search box that reports what was typed once the person pauses (250 ms), not on every key. */
export function SearchInput({ value, onChange, placeholder, label, className, delay = 250 }: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label: string;
  className?: string;
  delay?: number;
}) {
  const { t } = useI18n();
  const [text, setText] = useState(value);

  useEffect(() => setText(value), [value]);
  useEffect(() => {
    if (text === value) return;
    const timer = setTimeout(() => onChange(text), delay);
    return () => clearTimeout(timer);
  }, [text, value, onChange, delay]);

  return (
    <div className={clsx("relative", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden="true" />
      <input
        type="search"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className="h-10 w-full rounded-control border border-line bg-surface pl-9 pr-9 text-sm shadow-card placeholder:text-muted/70 hover:border-brand-600/40 focus:border-brand-600 [&::-webkit-search-cancel-button]:hidden"
      />
      {text && (
        <button
          type="button"
          onClick={() => { setText(""); onChange(""); }}
          aria-label={t("common.clear_filters")}
          className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-muted hover:bg-neutral-soft hover:text-ink"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

/** The Filters button and its panel. The filters apply as they change; the count says how many are set. */
export function FilterPopover({ active, onClear, children }: { active: number; onClear: () => void; children: ReactNode }) {
  const { t } = useI18n();
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <Button icon={<SlidersHorizontal className="h-4 w-4" aria-hidden="true" />}
                className={clsx(active > 0 && "border-brand-600/50 bg-brand-50 text-brand-800")}>
          {active > 0 ? t("common.filters_active", { count: active }) : t("common.filters")}
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          collisionPadding={16}
          className="z-40 w-[min(340px,calc(100vw-2rem))] rounded-card border border-line bg-surface p-4 shadow-pop animate-scale-in"
        >
          <div className="flex flex-col gap-4">{children}</div>
          <div className="mt-4 flex justify-end border-t border-line pt-3">
            <Button size="sm" variant="ghost" onClick={onClear} disabled={active === 0}>{t("common.clear_filters")}</Button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
