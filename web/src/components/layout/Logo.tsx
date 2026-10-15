import { clsx } from "clsx";

/** The mark of logo.jpg, redrawn as lines: a trunk that splits into four branches, each ending in a ring —
 * a cause-and-effect tree. It takes the current text colour, so it is white on the sidebar. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="80 40 620 660" className={clsx("shrink-0", className)} aria-hidden="true" fill="none"
         stroke="currentColor" strokeWidth={34} strokeLinecap="round">
      <path d="M390 670 V270 M390 270 L261 146 M390 270 L519 146 M390 490 L185 289 M390 490 L595 289" />
      <circle cx="223" cy="110" r="38" strokeWidth={28} />
      <circle cx="557" cy="110" r="38" strokeWidth={28} />
      <circle cx="148" cy="253" r="38" strokeWidth={28} />
      <circle cx="632" cy="253" r="38" strokeWidth={28} />
    </svg>
  );
}

export function Logo({ name, className, markClassName }: { name: string; className?: string; markClassName?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2.5 font-semibold tracking-tight", className)}>
      <LogoMark className={clsx("h-8 w-8", markClassName)} />
      <span>{name}</span>
    </span>
  );
}
