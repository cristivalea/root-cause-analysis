import { ChevronRight } from "lucide-react";
import { clsx } from "clsx";

/** How every clickable row of a list reacts (Problems, Analysis history, Expert check): it lifts a little,
 * its border and background turn blue, and the arrow at its end moves. Put "group" on the row. */
export const ROW_HOVER = clsx(
  "group transition-[background-color,border-color,box-shadow,transform] duration-150",
  "hover:-translate-y-px hover:border-brand-600/40 hover:bg-brand-50 hover:shadow-pop",
  "focus-within:ring-2 focus-within:ring-brand-600/40",
);

/** On a card whose title link covers the whole card ("stretched link"): the title is the one link, so the
 * card opens with a click anywhere, Enter on the title, or a middle click for a new tab. A link inside the
 * card that must stay clickable gets "relative z-10". */
export const STRETCHED_LINK = "outline-none after:absolute after:inset-0 after:rounded-card after:content-['']";

/** The arrow at the end of a clickable row: it says the row opens, and moves when the row is hovered. */
export function RowChevron({ className }: { className?: string }) {
  return (
    <ChevronRight
      className={clsx("h-5 w-5 shrink-0 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-brand-700", className)}
      aria-hidden="true"
    />
  );
}
