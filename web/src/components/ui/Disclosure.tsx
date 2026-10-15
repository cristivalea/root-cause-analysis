import { useState, type ReactNode } from "react";
import * as Collapsible from "@radix-ui/react-collapsible";
import { clsx } from "clsx";
import { ChevronDown } from "lucide-react";

/** An expandable section: a labelled button that shows or hides what is under it. */
export function Disclosure({ label, children, defaultOpen = false, className, compact = false, icon, count }: {
  label: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  compact?: boolean;
  icon?: ReactNode;
  count?: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className={className}>
      <Collapsible.Trigger
        className={clsx(
          "group inline-flex items-center gap-1.5 rounded-control text-left font-medium transition-colors",
          compact ? "text-xs text-muted hover:text-ink" : "py-1 text-sm text-brand-700 hover:text-brand-800",
        )}
      >
        {icon}
        <span>{label}</span>
        {count !== undefined && <span className="tabular rounded-full bg-neutral-soft px-1.5 text-xs text-muted">{count}</span>}
        <ChevronDown className="h-4 w-4 transition-transform duration-150 group-data-[state=open]:rotate-180" aria-hidden="true" />
      </Collapsible.Trigger>
      <Collapsible.Content className={clsx("animate-fade-in", compact ? "mt-1" : "mt-2")}>{children}</Collapsible.Content>
    </Collapsible.Root>
  );
}
