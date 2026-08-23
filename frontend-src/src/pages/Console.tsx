import { useEffect, useRef } from "react";
// The console markup is the ORIGINAL index.html body, carrying every element id,
// class, and data-attribute app.js binds to. It is imported as a raw string and
// injected rather than retyped as JSX, because a single mistyped id would
// silently detach a handler and break the safety-analysis flow.
import consoleMarkup from "@/legacy/console.html?raw";
import { installPregnancyDisplayRule } from "@/legacy/pregnancyDisplay";
import { installClinicalReference } from "@/legacy/clinicalReference";
import "@/styles/legacy.css";
import "@/styles/reference.css";

/**
 * The original vanilla console, rendered inside React.
 *
 * app.js is used VERBATIM. It is not ported, rewritten, or reimplemented, so the
 * prescription -> analysis -> warning -> evidence -> override -> analytics flow
 * is byte-for-byte the implementation that was already proven to work.
 *
 * Two facts about app.js drive everything here:
 *
 *   1. It captures its DOM references at module scope (app.js:25 onward), so the
 *      markup must already be in the document before the module is evaluated.
 *      Hence the dynamic import inside an effect, after the markup has rendered.
 *
 *   2. It boots from a DOMContentLoaded listener (app.js:78). That event has long
 *      since fired by the time React mounts, so it is re-dispatched once the
 *      module is loaded. Dispatching the event is what lets app.js stay unmodified.
 */
export default function Console() {
  const containerRef = useRef<HTMLDivElement>(null);
  const bootedRef = useRef(false);

  useEffect(() => {
    if (bootedRef.current) return;
    bootedRef.current = true;

    let cancelled = false;
    // Plain ES5 script, intentionally excluded from the TS project.
    import("@/legacy/app.js").then(() => {
      if (cancelled) return;
      document.dispatchEvent(new Event("DOMContentLoaded", { bubbles: false }));
      // Presentational rule layered on top of app.js's own rendering (section 16).
      installPregnancyDisplayRule();
      // Read-only browser over the ingested guideline corpus. Separate from
      // app.js so that file keeps its four-line diff against the original.
      installClinicalReference();
    });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      data-antibiotix-console=""
      dangerouslySetInnerHTML={{ __html: consoleMarkup }}
    />
  );
}
