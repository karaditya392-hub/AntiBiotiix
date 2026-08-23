/**
 * Clinical Reference browser.
 *
 * Surfaces the guideline corpus the backend already served but nothing displayed:
 * 82 conditions from the ICMR Treatment Guidelines 2022-23 edition and 29 from
 * the ICMR Standard Treatment Workflows 2022.
 *
 * Read-only. It calls two GET endpoints and renders what they return. It does not
 * touch the prescription, analysis, override or audit paths, and it lives outside
 * app.js so that file keeps its four-line diff against the original.
 *
 * Provenance is rendered for every entry, and deliberately not flattened: a page
 * in a hash-verified PDF and an operator-attested edition with no page are shown
 * as the different things they are.
 */

const STG_ENDPOINT = "/api/guidelines/stg-conditions";
const STW_ENDPOINT = "/api/guidelines/stw-conditions";

type Source = "stg" | "stw";

interface IndexRow {
  condition_key: string;
  condition_name: string;
  chapter?: string;
  specialty?: string;
  icd10?: string;
  infection_type?: string;
  source_document_id?: string;
  source_page?: number | null;
  attribution_basis?: string;
  prior_edition_cross_reference?: {
    document_id: string;
    page: number;
    section: string | null;
  } | null;
}

interface Entry extends IndexRow {
  __source: Source;
  __haystack: string;
}

const state: {
  entries: Entry[];
  filter: Source | "all";
  query: string;
  loaded: boolean;
  detailCache: Map<string, Record<string, unknown>>;
} = { entries: [], filter: "all", query: "", loaded: false, detailCache: new Map() };

function esc(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/** "oral_when_indicated" -> "Oral when indicated" */
function humanize(key: string): string {
  const s = key.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const SOURCE_LABEL: Record<Source, string> = {
  stg: "ICMR Treatment Guidelines 2022-23",
  stw: "ICMR Standard Treatment Workflows 2022",
};

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

async function loadCorpus(): Promise<void> {
  if (state.loaded) return;

  const [stg, stw] = await Promise.all([
    fetch(STG_ENDPOINT).then(r => r.json()),
    fetch(STW_ENDPOINT).then(r => r.json()),
  ]);

  const build = (rows: IndexRow[], source: Source): Entry[] =>
    rows.map(row => ({
      ...row,
      __source: source,
      __haystack: [
        row.condition_name, row.chapter, row.specialty, row.icd10,
        row.infection_type, row.condition_key,
      ].filter(Boolean).join(" ").toLowerCase(),
    }));

  state.entries = [
    ...build(stg.conditions || [], "stg"),
    ...build(stw.conditions || [], "stw"),
  ].sort((a, b) => a.condition_name.localeCompare(b.condition_name));

  state.loaded = true;

  const badge = document.getElementById("referenceCountBadge");
  if (badge) {
    badge.textContent = `${state.entries.length} conditions`;
  }

  const note = document.getElementById("referenceProvenanceNote");
  if (note && stg.authority_document) {
    const held = stg.authority_document.official_pdf_held;
    note.style.display = "";
    note.innerHTML =
      `<strong>How to read the sources below</strong>` +
      `<p>${esc(SOURCE_LABEL.stw)} is an official PDF held and hash-verified by this system, so its ` +
      `page numbers are real citations. ${esc(SOURCE_LABEL.stg)} is ` +
      `${held ? "held as an official PDF" : "operator-attested and not verifiable here"}: its entries carry ` +
      `no page in that edition, and where the same text also appears in the hash-verified 2019 edition that ` +
      `location is shown separately as a cross-reference, never as a page of the 2022-23 edition.</p>`;
  }
}

async function loadDetail(entry: Entry): Promise<Record<string, unknown>> {
  const cacheKey = `${entry.__source}:${entry.condition_key}`;
  const cached = state.detailCache.get(cacheKey);
  if (cached) return cached;

  const base = entry.__source === "stg" ? STG_ENDPOINT : STW_ENDPOINT;
  const res = await fetch(`${base}?condition=${encodeURIComponent(entry.condition_key)}`);
  const body = await res.json();
  const detail = (body.condition || {}) as Record<string, unknown>;
  state.detailCache.set(cacheKey, detail);
  return detail;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function visibleEntries(): Entry[] {
  const q = state.query.trim().toLowerCase();
  return state.entries.filter(e => {
    if (state.filter !== "all" && e.__source !== state.filter) return false;
    if (!q) return true;
    return e.__haystack.includes(q);
  });
}

function renderList(): void {
  const list = document.getElementById("referenceList");
  if (!list) return;

  const rows = visibleEntries();
  if (!rows.length) {
    list.innerHTML =
      `<div class="empty-state"><p>No condition matches that search.</p></div>`;
    return;
  }

  list.innerHTML = rows
    .map(e => {
      const sub = e.__source === "stg" ? e.chapter : [e.specialty, e.icd10].filter(Boolean).join(" · ");
      return (
        `<button class="reference-item" data-reference-key="${esc(e.__source)}:${esc(e.condition_key)}">` +
        `<span class="reference-item-name">${esc(e.condition_name)}</span>` +
        `<span class="reference-item-meta">${esc(sub || "")}</span>` +
        `<span class="reference-item-source ${esc(e.__source)}">${e.__source === "stg" ? "STG 2022-23" : "STW 2022"}</span>` +
        `</button>`
      );
    })
    .join("");
}

/** Renders arbitrarily-shaped medication/tier values without assuming a schema. */
function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) {
    return `<ul class="reference-ul">${value.map(v => `<li>${renderValue(v)}</li>`).join("")}</ul>`;
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) =>
        `<div class="reference-subfield"><span class="label">${esc(humanize(k))}</span>${renderValue(v)}</div>`)
      .join("");
  }
  return `<span>${esc(value)}</span>`;
}

function renderProvenance(entry: Entry, detail: Record<string, unknown>): string {
  const doc = esc((detail.source_document_id as string) || entry.source_document_id || "");
  const page = (detail.source_page ?? entry.source_page) as number | null;
  const xref = (detail.prior_edition_cross_reference ?? entry.prior_edition_cross_reference) as
    | { document_id: string; page: number; section: string | null }
    | null
    | undefined;
  const attribution = (detail.attribution_basis as string) || entry.attribution_basis;

  const bits: string[] = [
    `<div class="reference-subfield"><span class="label">Source document</span><span>${doc}</span></div>`,
  ];

  if (page) {
    bits.push(
      `<div class="reference-subfield"><span class="label">Page</span>` +
      `<span>p. ${esc(page)} <em class="reference-verified">verified against the held PDF</em></span></div>`
    );
  } else if (attribution === "OPERATOR_ATTESTATION") {
    bits.push(
      `<div class="reference-subfield"><span class="label">Page</span>` +
      `<span>Not available &mdash; no official PDF of this edition is held, so no page can be cited. ` +
      `Edition attribution is operator-attested and not verified by this system.</span></div>`
    );
  }

  if (xref) {
    bits.push(
      `<div class="reference-subfield"><span class="label">Prior edition cross-reference</span>` +
      `<span>${esc(xref.document_id)} &mdash; ${esc(xref.section || "")} (p. ${esc(xref.page)}). ` +
      `The same passage in the hash-verified 2019 edition. <em>Not a page of the 2022-23 edition.</em></span></div>`
    );
  }

  return bits.join("");
}

const DETAIL_ORDER: Array<[string, string]> = [
  ["presentation", "Clinical presentation"],
  ["organisms", "Common organisms"],
  ["severity_tiers", "By severity"],
  ["medications", "Medications"],
  ["duration", "Duration"],
  ["comments", "Comments"],
  ["caveat", "Caveat"],
  ["stewardship_note", "Stewardship note"],
  ["escalation", "Escalation"],
];

async function renderDetail(entry: Entry): Promise<void> {
  const pane = document.getElementById("referenceDetail");
  if (!pane) return;

  pane.innerHTML = `<div class="empty-state"><p>Loading&hellip;</p></div>`;
  let detail: Record<string, unknown>;
  try {
    detail = await loadDetail(entry);
  } catch {
    pane.innerHTML = `<div class="empty-state"><p>Could not load this condition.</p></div>`;
    return;
  }

  const header =
    `<div class="reference-detail-head">` +
    `<h4>${esc(detail.condition_name || entry.condition_name)}</h4>` +
    `<div class="reference-detail-tags">` +
    `<span class="badge badge-subtle">${esc(SOURCE_LABEL[entry.__source])}</span>` +
    (entry.icd10 ? `<span class="badge badge-mono">ICD-10 ${esc(entry.icd10)}</span>` : "") +
    (detail.chapter ? `<span class="badge badge-subtle">${esc(detail.chapter)}</span>` : "") +
    `</div></div>`;

  const sections = DETAIL_ORDER.filter(([k]) => detail[k] !== undefined && detail[k] !== null)
    .map(([k, label]) =>
      `<section class="reference-field"><h5>${esc(label)}</h5>${renderValue(detail[k])}</section>`)
    .join("");

  const verbatim = detail.verbatim_extract
    ? `<section class="reference-field"><h5>Source text</h5>` +
      `<blockquote class="reference-verbatim">${esc(detail.verbatim_extract)}</blockquote></section>`
    : "";

  pane.innerHTML =
    header + sections + verbatim +
    `<section class="reference-field"><h5>Provenance</h5>${renderProvenance(entry, detail)}</section>`;
  pane.scrollTop = 0;
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

let installed = false;

export function installClinicalReference(): void {
  if (installed) return;
  const tab = document.querySelector('[data-tab="tab-reference"]');
  if (!tab) return;
  installed = true;

  const activate = () => {
    loadCorpus().then(renderList).catch(() => {
      const list = document.getElementById("referenceList");
      if (list) {
        list.innerHTML =
          `<div class="empty-state"><p>The guideline corpus could not be loaded.</p></div>`;
      }
    });
  };

  // Load on first visit rather than at boot, so the tab costs nothing until used.
  tab.addEventListener("click", activate, { once: true });

  const search = document.getElementById("referenceSearchInput") as HTMLInputElement | null;
  search?.addEventListener("input", () => {
    state.query = search.value;
    renderList();
  });

  document.querySelectorAll<HTMLElement>("[data-reference-filter]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.filter = (btn.dataset.referenceFilter || "all") as Source | "all";
      document.querySelectorAll("[data-reference-filter]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      renderList();
    });
  });

  document.getElementById("referenceList")?.addEventListener("click", event => {
    const item = (event.target as HTMLElement).closest<HTMLElement>("[data-reference-key]");
    if (!item) return;
    document.querySelectorAll(".reference-item.active").forEach(el => el.classList.remove("active"));
    item.classList.add("active");
    const [source, key] = (item.dataset.referenceKey || "").split(":");
    const entry = state.entries.find(e => e.__source === source && e.condition_key === key);
    if (entry) void renderDetail(entry);
  });
}
