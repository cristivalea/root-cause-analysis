import { useState, type ReactNode } from "react";
import { clsx } from "clsx";

/** Chart colours. One series takes the accent; series that must be told apart take the categorical slots in
 * fixed order (blue, orange, aqua — checked with the dataviz validator for colour-blind separation). Text never
 * wears these colours: identity comes from the swatch beside the label. */
export const SERIES = { accent: "rgb(var(--brand-600))", rest: "#B9C3C0", blue: "#2a78d6", orange: "#eb6834", aqua: "#1baf7a" } as const;

/** The numbers of a chart as a table, for screen readers. The drawing hides its decorative parts from them; each
 * part that takes the keyboard focus (to show its tooltip) is an image named with its value. */
function NumbersTable({ caption, rows }: { caption: string; rows: [string, string][] }) {
  return (
    // a table ignores the 1px width of sr-only and grows with its text: the wrapper is what is hidden
    <div className="sr-only">
      <table>
        <caption>{caption}</caption>
        <tbody>{rows.map(([label, value]) => <tr key={label}><th scope="row">{label}</th><td>{value}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function Tip({ children }: { children: ReactNode }) {
  return (
    <span role="tooltip" className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 -translate-x-1/2 whitespace-nowrap rounded-control bg-ink px-2.5 py-1.5 text-xs text-white shadow-pop">
      {children}
    </span>
  );
}

export interface Bar {
  label: string;
  value: number;
  display: string;
  colour?: string;
  tip?: string;
}

/** Horizontal bars on one scale (0 to max), the value at the tip. Hover or focus shows the detail. */
export function BarList({ bars, max, caption }: { bars: Bar[]; max: number; caption: string }) {
  const [active, setActive] = useState<number | null>(null);
  return (
    <figure>
      <ul className="flex flex-col gap-3">
        {bars.map((bar, index) => (
          <li key={bar.label} className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] items-center gap-3 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)]">
            <span aria-hidden="true" className="truncate text-sm text-muted" title={bar.label}>{bar.label}</span>
            <span className="flex items-center gap-2">
              {/* a bar with no value (no case) is not drawn: its "—" says there is nothing to show */}
              {bar.value > 0 && <span
                tabIndex={0}
                role="img"
                aria-label={bar.tip ?? `${bar.label}: ${bar.display}`}
                onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(index)} onBlur={() => setActive(null)}
                className="relative block h-3.5 cursor-default rounded-r-[4px] outline-none transition-[filter] hover:brightness-110 focus-visible:ring-2 focus-visible:ring-brand-600"
                style={{ width: `${Math.max(1.5, Math.min(100, (bar.value / max) * 100))}%`, background: bar.colour ?? SERIES.accent }}
              >
                {active === index && <Tip>{bar.tip ?? `${bar.label}: ${bar.display}`}</Tip>}
              </span>}
              <span aria-hidden="true" className="tabular shrink-0 text-sm font-semibold text-ink">{bar.display}</span>
            </span>
          </li>
        ))}
      </ul>
      <NumbersTable caption={caption} rows={bars.map((bar) => [bar.label, bar.display])} />
    </figure>
  );
}

export interface Segment {
  label: string;
  value: number;
  colour: string;
}

/** One bar split into parts of a whole (2px surface gaps between the parts), with its legend. */
export function StackedBar({ segments, caption }: { segments: Segment[]; caption: string }) {
  const [active, setActive] = useState<number | null>(null);
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  const shown = segments.filter((item) => item.value > 0);
  return (
    <figure>
      <div className="flex h-4 w-full gap-[2px]">
        {shown.map((segment, index) => (
          <span
            key={segment.label}
            tabIndex={0}
            role="img"
            aria-label={`${segment.label}: ${segment.value} (${Math.round((segment.value / total) * 100)}%)`}
            onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(index)} onBlur={() => setActive(null)}
            className={clsx("relative h-full outline-none transition-[filter] hover:brightness-110 focus-visible:ring-2 focus-visible:ring-brand-600",
              index === 0 && "rounded-l-[4px]", index === shown.length - 1 && "rounded-r-[4px]")}
            style={{ width: `${(segment.value / total) * 100}%`, background: segment.colour }}
          >
            {active === index && <Tip>{segment.label}: {segment.value} ({Math.round((segment.value / total) * 100)}%)</Tip>}
          </span>
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-sm text-muted">
        {segments.map((segment) => (
          <li key={segment.label} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: segment.colour }} aria-hidden="true" />
            {segment.label} <span className="tabular font-semibold text-ink">{segment.value}</span>
          </li>
        ))}
      </ul>
      <NumbersTable caption={caption} rows={segments.map((segment) => [segment.label, String(segment.value)])} />
    </figure>
  );
}

export interface Column {
  key: string;
  label: string;
  parts: Segment[];
}

/** Stacked columns over time (one per week), with a hairline grid, a legend and a tooltip listing every part. */
export function Columns({ columns, caption, legend }: { columns: Column[]; caption: string; legend: Segment[] }) {
  const [active, setActive] = useState<number | null>(null);
  const top = Math.max(1, ...columns.map((column) => column.parts.reduce((sum, part) => sum + part.value, 0)));
  const ticks = top <= 4 ? Array.from({ length: top + 1 }, (_, index) => index) : [0, Math.round(top / 2), top];
  const height = 160;
  return (
    <figure>
      <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1.5 text-sm text-muted">
        {legend.map((item) => (
          <li key={item.label} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: item.colour }} aria-hidden="true" />{item.label}
          </li>
        ))}
      </ul>
      <div className="relative pl-7" style={{ height: height + 28 }}>
        {ticks.map((tick) => (
          <div key={tick} aria-hidden="true" className="absolute left-7 right-0 border-t border-line" style={{ bottom: 28 + (tick / top) * height }}>
            <span className="tabular absolute -left-7 -top-2 w-5 text-right text-[11px] text-muted">{tick}</span>
          </div>
        ))}
        <div className="absolute bottom-7 left-7 right-0 flex h-[160px] items-end justify-around gap-2">
          {columns.map((column, index) => (
            <div key={column.key} className="relative flex h-full w-full max-w-[56px] flex-col items-center justify-end">
              <div
                tabIndex={0}
                role="img"
                aria-label={[column.label, ...column.parts.map((part) => `${part.value} · ${part.label}`)].join(", ")}
                onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(index)} onBlur={() => setActive(null)}
                className="relative flex w-6 cursor-default flex-col-reverse gap-[2px] outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
              >
                {column.parts.filter((part) => part.value > 0).map((part, position, list) => (
                  <span key={part.label} className={clsx("block w-full", position === list.length - 1 && "rounded-t-[4px]")}
                        style={{ height: (part.value / top) * height - 2, background: part.colour }} />
                ))}
                {active === index && (
                  <Tip>
                    <span className="block font-semibold">{column.label}</span>
                    {column.parts.map((part) => (
                      <span key={part.label} className="flex items-center gap-1.5">
                        <span className="h-0.5 w-3" style={{ background: part.colour }} />{part.value} · {part.label}
                      </span>
                    ))}
                  </Tip>
                )}
              </div>
              <span aria-hidden="true" className="absolute -bottom-6 whitespace-nowrap text-[11px] text-muted">{column.key}</span>
            </div>
          ))}
        </div>
      </div>
      <NumbersTable caption={caption} rows={columns.flatMap((column) => column.parts.map((part) => [`${column.label} · ${part.label}`, String(part.value)] as [string, string]))} />
    </figure>
  );
}
