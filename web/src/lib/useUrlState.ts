import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** List state kept in the address (tab, page, search, filters), so a reload or a shared link shows the same
 * list. Changing anything but the page goes back to page 1. */
export function useUrlState<K extends string>(defaults: Record<K, string>) {
  const [params, setParams] = useSearchParams();

  const value = (key: K): string => params.get(key) ?? defaults[key];

  const set = useCallback(
    (changes: Partial<Record<K, string>>) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, item] of Object.entries(changes) as [K, string | undefined][]) {
            if (item === undefined || item === "" || item === defaults[key]) next.delete(key);
            else next.set(key, item);
          }
          if (!("page" in changes)) next.delete("page");
          return next;
        },
        { replace: true },
      );
    },
    [setParams, defaults],
  );

  return { value, set };
}

/** Pagination over a list already filtered: the page is clamped, so a shrinking list never shows an empty page. */
export function paginate<T>(items: T[], page: number, size: number) {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(Math.max(1, page), pages);
  return { items: items.slice((current - 1) * size, current * size), page: current, pages };
}
