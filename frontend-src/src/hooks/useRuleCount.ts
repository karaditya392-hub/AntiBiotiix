import { useEffect, useState } from "react";

/**
 * How many clinical rules the engine actually holds.
 *
 * The count was hardcoded as "24" in six places. It was correct when written and
 * silently became wrong the moment two rules were added, which is the same failure
 * the API layer already guards against by reading guideline editions out of the
 * corpus instead of restating them from memory (see backend/app.py
 * _ingested_editions). A number printed next to a safety claim has to come from
 * the thing it describes.
 *
 * Returns null until the count is known. Callers render a label without a number
 * in that case rather than guessing one, because a wrong count is worse than no
 * count.
 */
let cached: number | null = null;

export function useRuleCount(): number | null {
  const [count, setCount] = useState<number | null>(cached);

  useEffect(() => {
    if (cached !== null) return;
    let cancelled = false;
    fetch("/api/guidelines/rules")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        const total = typeof d?.total_rules === "number" ? d.total_rules : null;
        if (total !== null) {
          cached = total;
          if (!cancelled) setCount(total);
        }
      })
      .catch(() => {
        /* A failed count must never break the page it labels. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return count;
}

/** "26-Rule Engine", or "Rule Engine" while the count is unknown. */
export function ruleEngineLabel(count: number | null): string {
  return count === null ? "Rule Engine" : `${count}-Rule Engine`;
}
