import { useCallback, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { clsx } from "clsx";
import { Maximize2, Minus, Plus } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

const STEPS = [0.5, 0.6, 0.7, 0.8, 0.9, 1, 1.1, 1.25];

/** A framed canvas for a diagram, like the mymap.ai example: the diagram is fitted into a box of bounded
 * height, with zoom and Fit controls, so it never takes over the page. */
export function DiagramFrame({ children, maxHeight = 520, label, className }: {
  children: ReactNode;
  maxHeight?: number;
  label: string;
  className?: string;
}) {
  const { t } = useI18n();
  const frameRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [fitted, setFitted] = useState(true);
  const [size, setSize] = useState({ width: 0, height: 0 });

  const fit = useCallback(() => {
    const frame = frameRef.current;
    const content = contentRef.current;
    if (!frame || !content) return;
    const width = content.scrollWidth;
    const height = content.scrollHeight;
    setSize({ width, height });
    const room = frame.clientWidth - 32;
    // fitted to the width; to the height too, but never below 80 %: smaller text stops being readable,
    // and the frame scrolls instead
    setScale(Math.min(1, room / width, Math.max(0.8, (maxHeight - 72) / height)));
  }, [maxHeight]);

  useLayoutEffect(() => {
    if (!fitted) return;
    fit();
    const observer = new ResizeObserver(fit);
    if (frameRef.current) observer.observe(frameRef.current);
    if (contentRef.current) observer.observe(contentRef.current);
    return () => observer.disconnect();
  }, [fitted, fit]);

  const zoom = (direction: 1 | -1) => {
    setFitted(false);
    if (contentRef.current) setSize({ width: contentRef.current.scrollWidth, height: contentRef.current.scrollHeight });
    setScale((current) => {
      const index = STEPS.findIndex((step) => step >= current - 0.001);
      const next = STEPS[Math.min(STEPS.length - 1, Math.max(0, (index === -1 ? STEPS.length - 1 : index) + direction))];
      return next ?? current;
    });
  };

  const control = "inline-flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-brand-50 hover:text-ink";
  return (
    <figure
      aria-label={label}
      className={clsx("relative overflow-hidden rounded-card border border-line bg-[radial-gradient(circle,rgb(var(--line))_1px,transparent_1px)] [background-size:18px_18px]", className)}
    >
      {/* focusable, so a keyboard user can scroll a diagram larger than its frame with the arrow keys */}
      <div
        ref={frameRef}
        tabIndex={0}
        className="overflow-auto px-4 pb-14 pt-10 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-600"
        style={{ maxHeight }}
      >
        <div
          className="mx-auto"
          style={{ width: size.width ? size.width * scale : undefined, height: size.height ? size.height * scale : undefined }}
        >
          <div ref={contentRef} className="w-max origin-top-left" style={{ transform: `scale(${scale})` }}>
            {children}
          </div>
        </div>
      </div>
      <div className="absolute bottom-3 right-3 flex items-center gap-0.5 rounded-control border border-line bg-surface/95 p-0.5 shadow-card backdrop-blur">
        <button type="button" className={control} onClick={() => zoom(-1)} aria-label={t("diagram.zoom_out")}>
          <Minus className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
        <span className="tabular w-10 text-center text-xs font-medium text-muted" aria-live="polite">{Math.round(scale * 100)}%</span>
        <button type="button" className={control} onClick={() => zoom(1)} aria-label={t("diagram.zoom_in")}>
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
        <button type="button" className={clsx(control, "w-auto gap-1 px-2 text-xs font-medium")} onClick={() => setFitted(true)}
                aria-pressed={fitted}>
          <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
          {t("diagram.fit")}
        </button>
      </div>
    </figure>
  );
}
