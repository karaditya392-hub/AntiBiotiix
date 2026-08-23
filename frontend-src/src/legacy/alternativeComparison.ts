/**
 * Comparative alternative-antibiotic analysis.
 *
 * Answers "what changes if I select an alternative?" by running the SAME
 * deterministic safety engine against an alternative agent for the same patient,
 * and showing the two results side by side.
 *
 * Design constraints this works within:
 *
 *  - The backend is immutable, so there is no dry-run mode. A comparison creates
 *    a real prescription record. Its diagnosis is therefore tagged so the audit
 *    trail shows the record was an exploration, not a dispensed order, and the
 *    alert-fatigue table carries a matching caveat about inflated trigger counts.
 *
 *  - app.js is untouched. The current prescription and its analysis are captured
 *    by observing fetch traffic rather than by reading app.js's module state,
 *    which is not exported.
 *
 *  - It never recommends. It reports what the engine returned for each option and
 *    states plainly that the choice remains the clinician's.
 */

const COMPARATIVE_TAG = "[COMPARATIVE WHAT-IF - NOT A DISPENSED ORDER]";

interface Warning {
  rule_id: string;
  severity: string;
  title?: string;
  clinical_concern?: string;
  prescribed_drug?: string;
}

interface Analysis {
  prescription_id: string;
  diagnosis: string;
  items: Array<{ medication_name: string }>;
  warnings: Warning[];
  critical_warnings_count: number;
  high_warnings_count: number;
  moderate_warnings_count: number;
  stewardship_summary: {
    stewardship_priority: { tier: string };
    aware_breakdown: Record<string, string>;
  };
  local_amr_context: Array<{
    organism: string;
    antimicrobial: string;
    resistance_rate_pct: number;
    sample_size: number;
    clinical_implication?: string;
  }>;
}

/** Last prescription payload app.js POSTed, and the analysis that came back. */
const observed: { payload: Record<string, unknown> | null; analysis: Analysis | null } = {
  payload: null,
  analysis: null,
};

function esc(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// ---------------------------------------------------------------------------
// Observing the live prescription, without touching app.js
// ---------------------------------------------------------------------------

function installFetchObserver(): void {
  const original = window.fetch;
  window.fetch = async function (...args: Parameters<typeof fetch>): Promise<Response> {
    const [input, init] = args;
    const url = typeof input === "string" ? input : (input as Request).url ?? String(input);
    const response = await original(...args);

    try {
      if (url.includes("/api/prescriptions") && !url.includes("/extract") && init?.method === "POST"
          && !url.includes("/analyze") && typeof init.body === "string") {
        const body = JSON.parse(init.body);
        // Ignore our own comparison submissions.
        if (!String(body.diagnosis || "").includes(COMPARATIVE_TAG)) {
          observed.payload = body;
        }
      }
      if (url.includes("/analyze") && init?.method === "POST") {
        const clone = response.clone();
        clone.json().then((data: Analysis) => {
          if (!String(data.diagnosis || "").includes(COMPARATIVE_TAG)) {
            observed.analysis = data;
            revealPanel();
          }
        }).catch(() => undefined);
      }
    } catch {
      /* observation must never break the request it is watching */
    }
    return response;
  } as typeof fetch;
}

function revealPanel(): void {
  const panel = document.getElementById("comparePanel");
  if (!panel) return;
  panel.classList.remove("hidden");
  renderSuggestions();
}

// ---------------------------------------------------------------------------
// Suggestions
// ---------------------------------------------------------------------------

/**
 * Common alternatives, offered purely as shortcuts for typing. This list does not
 * rank, score or recommend: whatever is chosen is analysed by the same engine and
 * reported as-is, including when the result is worse than the current choice.
 */
const SUGGESTIONS = [
  "Azithromycin 500mg PO OD x 3 days",
  "Doxycycline 100mg PO BD x 7 days",
  "Levofloxacin 750mg PO OD x 5 days",
  "Ceftriaxone 1g IV OD x 7 days",
  "Co-trimoxazole 2 DS tablets PO BD x 7 days",
];

function renderSuggestions(): void {
  const host = document.getElementById("compareSuggestions");
  if (!host || host.dataset.rendered) return;
  host.dataset.rendered = "1";
  host.innerHTML =
    `<span class="preset-label">Quick alternatives:</span>` +
    SUGGESTIONS.map(s =>
      `<button class="btn btn-chip" data-compare-suggest="${esc(s)}">${esc(s.split(" ")[0])}</button>`
    ).join("");
  host.addEventListener("click", e => {
    const btn = (e.target as HTMLElement).closest<HTMLElement>("[data-compare-suggest]");
    if (!btn) return;
    const input = document.getElementById("compareInput") as HTMLInputElement | null;
    if (input) input.value = btn.dataset.compareSuggest || "";
  });
}

// ---------------------------------------------------------------------------
// Running the comparison
// ---------------------------------------------------------------------------

async function runComparison(): Promise<void> {
  const input = document.getElementById("compareInput") as HTMLInputElement | null;
  const results = document.getElementById("compareResults");
  const btn = document.getElementById("compareRunBtn") as HTMLButtonElement | null;
  if (!input || !results) return;

  const text = input.value.trim();
  if (!text) {
    results.innerHTML = `<p class="sub-text">Enter an alternative agent to compare.</p>`;
    return;
  }
  if (!observed.payload || !observed.analysis) {
    results.innerHTML = `<p class="sub-text">Analyse a prescription first, then compare.</p>`;
    return;
  }

  if (btn) { btn.disabled = true; btn.textContent = "Running…"; }
  results.innerHTML = `<p class="sub-text">Running the safety engine against the alternative…</p>`;

  try {
    // Parse the alternative with the SAME extraction endpoint the main flow uses,
    // so dose, route, frequency and duration are interpreted identically.
    const extractRes = await fetch("/api/prescriptions/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_text: text }),
    });
    const extracted = await extractRes.json();
    const items = (extracted.items && extracted.items.length)
      ? extracted.items
      : [{ medication_name: text }];

    const base = observed.payload as Record<string, unknown>;
    const createRes = await fetch("/api/prescriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...base,
        // Tagged so the audit trail shows this record was an exploration. The tag
        // is appended, never prefixed, so syndrome matching still sees the
        // original diagnosis text first.
        diagnosis: `${base.diagnosis} ${COMPARATIVE_TAG}`,
        raw_text: text,
        items,
      }),
    });
    const created = await createRes.json();

    const analyzeRes = await fetch(`/api/prescriptions/${created.prescription_id}/analyze`, {
      method: "POST",
    });
    const alternative: Analysis = await analyzeRes.json();

    renderComparison(observed.analysis, alternative);
  } catch (err) {
    results.innerHTML =
      `<p class="sub-text">Comparison failed: ${esc((err as Error).message)}</p>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Run comparative analysis"; }
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

const CHECKS: Array<[string, string]> = [
  ["ALLERGY", "documented allergy conflict"],
  ["DUP", "therapeutic duplication"],
  ["RENAL", "renal dose concern"],
  ["HEPATIC", "hepatic dose concern"],
  ["DDI", "drug-drug interaction"],
  ["VULN", "vulnerable-population concern"],
];

function drugsOf(a: Analysis): string {
  return a.items.map(i => i.medication_name).join(", ");
}

function findingsFor(a: Analysis): string {
  const rows: string[] = [];

  for (const [prefix, label] of CHECKS) {
    const hits = a.warnings.filter(w => w.rule_id.startsWith(prefix));
    if (hits.length) {
      const worst = hits.some(w => w.severity === "CRITICAL") ? "critical"
        : hits.some(w => w.severity === "HIGH") ? "high" : "moderate";
      rows.push(
        `<li class="compare-flag ${worst}"><span class="compare-mark" aria-hidden="true">!</span>` +
        `<span>${esc(hits[0].clinical_concern || label)} ` +
        `<em class="compare-rule">${esc(hits.map(h => h.rule_id).join(", "))}</em></span></li>`
      );
    } else {
      rows.push(
        `<li class="compare-ok"><span class="compare-mark" aria-hidden="true">✓</span>` +
        `<span>No ${esc(label)}</span></li>`
      );
    }
  }

  // Rules outside the mapped families (coverage fail-safe, stewardship, diagnosis).
  const mapped = CHECKS.map(c => c[0]);
  for (const w of a.warnings.filter(w => !mapped.some(p => w.rule_id.startsWith(p)))) {
    rows.push(
      `<li class="compare-flag ${esc(w.severity.toLowerCase())}">` +
      `<span class="compare-mark" aria-hidden="true">!</span>` +
      `<span>${esc(w.clinical_concern || w.title || w.rule_id)} ` +
      `<em class="compare-rule">${esc(w.rule_id)}</em></span></li>`
    );
  }

  // Local resistance context is a consideration, not a rule finding.
  for (const amr of a.local_amr_context || []) {
    rows.push(
      `<li class="compare-flag moderate"><span class="compare-mark" aria-hidden="true">!</span>` +
      `<span>Local resistance: ${esc(amr.organism)} &mdash; ` +
      `<strong>${esc(amr.resistance_rate_pct)}%</strong> to ${esc(amr.antimicrobial)} ` +
      `(n=${esc(amr.sample_size)}). ${esc(amr.clinical_implication || "")}</span></li>`
    );
  }

  return `<ul class="compare-findings">${rows.join("")}</ul>`;
}

function column(a: Analysis, kind: "current" | "alternative"): string {
  const tier = a.stewardship_summary?.stewardship_priority?.tier || "—";
  const aware = Object.values(a.stewardship_summary?.aware_breakdown || {})
    .filter(v => v && v !== "NOT_APPLICABLE");
  const counts =
    `<span class="compare-count critical">${a.critical_warnings_count} critical</span>` +
    `<span class="compare-count high">${a.high_warnings_count} high</span>` +
    `<span class="compare-count moderate">${a.moderate_warnings_count} moderate</span>`;

  return (
    `<div class="compare-column ${kind}">` +
    `<div class="compare-column-head">` +
    `<span class="compare-kind">${kind === "current" ? "Current prescription" : "Alternative"}</span>` +
    `<strong>${esc(drugsOf(a))}</strong>` +
    `<div class="compare-badges">${counts}` +
    `<span class="compare-count tier">Tier ${esc(tier)}</span>` +
    (aware.length ? `<span class="compare-count aware">AWaRe ${esc(aware.join(", "))}</span>` : "") +
    `</div></div>` +
    findingsFor(a) +
    `</div>`
  );
}

function renderComparison(current: Analysis, alternative: Analysis): void {
  const results = document.getElementById("compareResults");
  if (!results) return;
  results.innerHTML =
    `<div class="compare-grid">${column(current, "current")}${column(alternative, "alternative")}</div>`;
}

// ---------------------------------------------------------------------------

let installed = false;

export function installAlternativeComparison(): void {
  if (installed) return;
  if (!document.getElementById("comparePanel")) return;
  installed = true;

  installFetchObserver();

  document.getElementById("compareRunBtn")?.addEventListener("click", () => void runComparison());
  document.getElementById("compareInput")?.addEventListener("keydown", e => {
    if ((e as KeyboardEvent).key === "Enter") void runComparison();
  });
}
