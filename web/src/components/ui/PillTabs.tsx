import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { clsx } from "clsx";

export interface PillTab<T extends string> {
  value: T;
  label: string;
  count?: number;
}

/** Rounded tabs with a pill that slides to the chosen one (the pattern of Aceternity's tabs). Arrow keys move
 * between tabs (Radix). The panel shows only the chosen tab, rendered by the caller as children. */
export function PillTabs<T extends string>({ tabs, value, onChange, label, children, className }: {
  tabs: PillTab<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  children?: ReactNode;
  className?: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const [pill, setPill] = useState<{ left: number; top: number; width: number; height: number } | null>(null);

  useLayoutEffect(() => {
    const update = () => {
      const active = listRef.current?.querySelector<HTMLElement>('[data-state="active"]');
      if (active) setPill({ left: active.offsetLeft, top: active.offsetTop, width: active.offsetWidth, height: active.offsetHeight });
    };
    update();
    const observer = new ResizeObserver(update);
    if (listRef.current) observer.observe(listRef.current);
    return () => observer.disconnect();
  }, [value, tabs]);

  return (
    <Tabs.Root value={value} onValueChange={(next) => onChange(next as T)} className={className}>
      <div className="-mx-1 px-1 pb-1">
        {/* many tabs wrap onto a second row instead of hiding behind a scroll */}
        <Tabs.List
          ref={listRef}
          aria-label={label}
          className="relative inline-flex max-w-full flex-wrap items-center gap-1 rounded-[22px] border border-line bg-surface p-1 shadow-card"
        >
          {pill && (
            <span
              aria-hidden="true"
              className="absolute rounded-full bg-brand-600 shadow-card transition-all duration-200 ease-out"
              style={{ left: pill.left, top: pill.top, width: pill.width, height: pill.height }}
            />
          )}
          {tabs.map((tab) => (
            <Tabs.Trigger
              key={tab.value}
              value={tab.value}
              className={clsx(
                "relative z-10 inline-flex h-8 items-center gap-2 rounded-full px-4 text-sm font-medium transition-colors duration-200",
                "text-muted hover:text-ink data-[state=active]:text-white",
              )}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className="tabular rounded-full bg-black/5 px-1.5 text-xs font-semibold [[data-state=active]_&]:bg-white [[data-state=active]_&]:text-brand-700">
                  {tab.count}
                </span>
              )}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
      </div>
      {children !== undefined ? (
        <Tabs.Content value={value} className="mt-5 outline-none" tabIndex={-1}>
          {children}
        </Tabs.Content>
      ) : (
        // used as a filter, the content is the rest of the page: an empty panel keeps aria-controls valid
        <Tabs.Content value={value} hidden />
      )}
    </Tabs.Root>
  );
}
