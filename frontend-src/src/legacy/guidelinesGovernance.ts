/**
 * Guidelines tab: cross-source comparison and rule governance.
 *
 * Both live outside app.js so that file keeps its four-line diff against the
 * original, and neither touches the prescription, analysis or override paths.
 *
 * The clinician role is read from the console's existing role selector and sent
 * as the bearer token, exactly as app.js does for overrides, so authorization is
 * enforced server-side and an unauthorized role is rejected with 403 rather than
 * being hidden in the UI.
 */

const ROLE_TOKENS: Record<string, string> = {
  ATTENDING_PHYSICIAN: "mock_attending_token",
  INFECTIOUS_DISEASE_SPECIALIST: "mock_id_token",
  CLINICAL_PHARMACIST: "mock_pharmacist_token",
  RESIDENT_PHYSICIAN: "mock_resident_token",
  STAFF_NURSE: "mock_nurse_token",
};

function currentRole(): string {
  const sel = document.getElementById("clinicianRoleSelect") as HTMLSelectElement | null;
  return sel?.value || "ATTENDING_PHYSICIAN";
}

function authHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${ROLE_TOKENS[currentRole()] || "mock_attending_token"}`,
  };
}

function esc(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function toast(message: string, type: "success" | "danger" | "warning" = "success"): void {
  // app.js owns the toast implementation; reuse it when present rather than
  // introducing a second notification style.
  const fn = (window as unknown as { showToast?: (m: string, t: string) => void }).showToast;
  if (typeof fn === "function") { fn(message, type); return; }
  console.info(`[${type}] ${message}`);
}

// ---------------------------------------------------------------------------
// Cross-source comparison
// ---------------------------------------------------------------------------

interface Passage {
  document_title: string;
  section_page: string;
  verbatim_passage: string;
  page_reference_kind: string;
  provenance_basis: string;
  retrieval_score: number;
}

interface SourceDoc {
  document_id: string;
  title: string;
  version: string;
  precedence_rank: number | null;
  provenance_basis: string;
  has_guidance: boolean;
  reason?: string;
  nearest_score?: number | null;
  top_score?: number;
  passages: Passage[];
  named_drugs: string[];
}

function renderCrossSource(data: {
  available: boolean;
  message?: string;
  topic: string;
  documents_searched: number;
  documents_with_guidance: number;
  documents: SourceDoc[];
  differing_agents: Array<{ drug: string; named_by: string[]; not_named_by: string[] }>;
  curated_conflict: Record<string, string> | null;
  interpretation_note: string;
}): void {
  const host = document.getElementById("crossSourceResults");
  if (!host) return;

  if (!data.available) {
    host.innerHTML = `<p class="sub-text">${esc(data.message)}</p>`;
    return;
  }

  const onTopic = data.documents.filter(d => d.has_guidance);
  const silent = data.documents.filter(d => !d.has_guidance);

  const header =
    `<div class="cross-summary">` +
    `<span class="badge badge-mono">${onTopic.length} of ${data.documents_searched} sources cover this topic</span>` +
    (data.differing_agents.length
      ? `<span class="badge badge-warning">${data.differing_agents.length} agent(s) named by some sources and not others</span>`
      : `<span class="badge badge-subtle">No difference in named agents</span>`) +
    `</div>`;

  const curated = data.curated_conflict
    ? `<div class="cross-curated">` +
      `<strong>Curated conflict on record &mdash; ${esc(data.curated_conflict.topic)}</strong>` +
      `<p><span class="label">National (ICMR)</span>${esc(data.curated_conflict.national_icmr)}</p>` +
      `<p><span class="label">International</span>${esc(data.curated_conflict.international_note)}</p>` +
      `<p><span class="label">Resolution</span>${esc(data.curated_conflict.resolved_precedence_ruling)}</p>` +
      `<em>Reviewed and written down by a clinician, not inferred by the system.</em>` +
      `</div>`
    : "";

  const columns = onTopic.map(d => {
    const verified = d.provenance_basis === "HASH_VERIFIED_PDF";
    return (
      `<article class="cross-doc">` +
      `<header>` +
      `<span class="cross-rank">Precedence rank ${esc(d.precedence_rank ?? "—")}</span>` +
      `<strong>${esc(d.title)}</strong>` +
      `<span class="cross-version">${esc(d.version)}</span>` +
      `<span class="cross-prov ${verified ? "verified" : "attested"}">` +
      `${verified ? "hash-verified source" : "operator-attested source"}</span>` +
      `</header>` +
      (d.named_drugs.length
        ? `<div class="cross-drugs">${d.named_drugs.map(x => `<span class="tag">${esc(x)}</span>`).join("")}</div>`
        : `<div class="cross-drugs"><span class="sub-text">No formulary agent named in the retrieved passages.</span></div>`) +
      d.passages.map(p =>
        `<blockquote class="cross-passage">${esc(p.verbatim_passage)}` +
        `<cite>${esc(p.section_page)}</cite></blockquote>`).join("") +
      `</article>`
    );
  }).join("");

  const silentList = silent.length
    ? `<details class="cross-silent"><summary>${silent.length} source(s) had nothing on this topic</summary>` +
      `<ul>${silent.map(d =>
        `<li>${esc(d.title)} <em>${esc(d.reason || "")}` +
        (d.nearest_score != null ? ` (nearest match ${esc(d.nearest_score)})` : "") +
        `</em></li>`).join("")}</ul></details>`
    : "";

  const differing = data.differing_agents.length
    ? `<div class="cross-differ"><h5>Agents named by some sources but not others</h5>` +
      `<ul>${data.differing_agents.map(x =>
        `<li><strong>${esc(x.drug)}</strong> &mdash; named by ${esc(x.named_by.length)}, ` +
        `not named by ${esc(x.not_named_by.length)} <em>${esc(x.named_by.join(", "))}</em></li>`).join("")}</ul></div>`
    : "";

  host.innerHTML =
    header + curated +
    `<div class="cross-grid">${columns}</div>` +
    differing + silentList +
    `<p class="cross-note">${esc(data.interpretation_note)}</p>`;
}

async function runCrossSource(): Promise<void> {
  const input = document.getElementById("crossSourceInput") as HTMLInputElement | null;
  const host = document.getElementById("crossSourceResults");
  const btn = document.getElementById("crossSourceBtn") as HTMLButtonElement | null;
  if (!input || !host) return;

  const topic = input.value.trim();
  if (!topic) {
    host.innerHTML = `<p class="sub-text">Enter a syndrome or therapy topic to compare.</p>`;
    return;
  }

  if (btn) { btn.disabled = true; btn.textContent = "Comparing…"; }
  host.innerHTML = `<p class="sub-text">Searching every ingested document…</p>`;
  try {
    const res = await fetch(`/api/guidelines/cross-source?topic=${encodeURIComponent(topic)}`);
    renderCrossSource(await res.json());
  } catch (err) {
    host.innerHTML = `<p class="sub-text">Comparison failed: ${esc((err as Error).message)}</p>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Compare across sources"; }
  }
}

// ---------------------------------------------------------------------------
// Rule governance
// ---------------------------------------------------------------------------

interface GovRule {
  rule_id: string;
  severity: string;
  catalog_status: string;
  effective_status: string;
  reviewed: boolean;
  reviewed_by: string | null;
  reviewer_role: string | null;
  review_rationale: string | null;
  last_action: string | null;
}

const STATUS_CLASS: Record<string, string> = {
  APPROVED_FOR_CLINICAL_USE: "gov-approved",
  REJECTED_IN_REVIEW: "gov-rejected",
  CHANGES_REQUESTED: "gov-changes",
  RETIRED: "gov-retired",
  PENDING_CLINICAL_REVIEW: "gov-pending",
};

async function loadGovernance(): Promise<void> {
  const body = document.getElementById("governanceTableBody");
  const badge = document.getElementById("governanceSummaryBadge");
  if (!body) return;

  try {
    const data = await fetch("/api/rules/governance").then(r => r.json());
    if (badge) {
      badge.textContent =
        `${data.approved_count} approved · ${data.pending_count} pending of ${data.total_rules}`;
    }

    body.innerHTML = (data.rules as GovRule[]).map(r => {
      const cls = STATUS_CLASS[r.effective_status] || "gov-pending";
      return (
        `<tr>` +
        `<td class="val-mono">${esc(r.rule_id)}</td>` +
        `<td>${esc(r.severity)}</td>` +
        `<td><span class="sub-text">${esc(r.catalog_status)}</span></td>` +
        `<td><span class="gov-status ${cls}">${esc(r.effective_status.replace(/_/g, " "))}</span></td>` +
        `<td>${r.reviewed
          ? `${esc(r.reviewed_by)}<br><span class="sub-text">${esc(r.reviewer_role)}</span>`
          : `<span class="sub-text">Not yet reviewed</span>`}</td>` +
        `<td><button class="btn btn-chip" data-review-rule="${esc(r.rule_id)}">` +
        `${r.reviewed ? "Re-review" : "Record review"}</button></td>` +
        `</tr>`
      );
    }).join("");
  } catch {
    body.innerHTML = `<tr><td colspan="6" class="text-center">Could not load rule governance state.</td></tr>`;
  }
}

async function submitReview(ruleId: string): Promise<void> {
  const action = window.prompt(
    `Record a review decision for ${ruleId}.\n\n` +
    `Type one of: APPROVED, REJECTED, CHANGES_REQUESTED, RETIRED`,
    "APPROVED"
  );
  if (!action) return;

  const rationale = window.prompt(
    `Clinical rationale for ${action} on ${ruleId}.\n\n` +
    `Recorded permanently in the immutable audit trail. Minimum 10 characters.`,
    ""
  );
  if (!rationale) return;

  try {
    const res = await fetch(`/api/rules/${encodeURIComponent(ruleId)}/review`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ action: action.trim().toUpperCase(), rationale: rationale.trim() }),
    });
    const data = await res.json();
    if (!res.ok) {
      toast(data.detail || `Review rejected (${res.status})`, "danger");
      return;
    }
    toast(`${ruleId}: ${data.action} recorded by ${data.reviewer_role}.`, "success");
    await loadGovernance();
  } catch (err) {
    toast(`Review failed: ${(err as Error).message}`, "danger");
  }
}

// ---------------------------------------------------------------------------

let installed = false;

export function installGuidelinesGovernance(): void {
  if (installed) return;
  const tab = document.querySelector('[data-tab="tab-guidelines"]');
  if (!tab || !document.getElementById("ruleGovernanceCard")) return;
  installed = true;

  // Load on first visit; the tab costs nothing until opened.
  tab.addEventListener("click", () => void loadGovernance(), { once: true });

  document.getElementById("crossSourceBtn")?.addEventListener("click", () => void runCrossSource());
  document.getElementById("crossSourceInput")?.addEventListener("keydown", e => {
    if ((e as KeyboardEvent).key === "Enter") void runCrossSource();
  });

  document.querySelectorAll<HTMLElement>("[data-cross-topic]").forEach(btn => {
    btn.addEventListener("click", () => {
      const input = document.getElementById("crossSourceInput") as HTMLInputElement | null;
      if (input) { input.value = btn.dataset.crossTopic || ""; void runCrossSource(); }
    });
  });

  document.getElementById("governanceTableBody")?.addEventListener("click", e => {
    const btn = (e.target as HTMLElement).closest<HTMLElement>("[data-review-rule]");
    if (btn) void submitReview(btn.dataset.reviewRule || "");
  });
}
