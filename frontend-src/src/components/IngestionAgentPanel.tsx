import { useEffect, useState } from "react";
import {
  AlertTriangle, CheckCircle2, Download, FileText, ShieldAlert, Upload, XCircle,
} from "lucide-react";
import AgentFlowGraph, { type FlowGraph, type Trace } from "@/components/AgentFlowGraph";
import { useAuth } from "@/context/AuthContext";
import "@/styles/agent-flow.css";

/**
 * The document ingestion agent, run and rendered.
 *
 * THE PART OF THIS UI THAT MATTERS IS NOT THE FILE PICKER. It is the three
 * panels beneath it:
 *
 *   1. THE VALIDATION REPORT. Every guardrail, passed or failed, with the reason.
 *      A refused document is the safety behaviour working, so the refusal is
 *      rendered in full rather than reduced to "upload failed".
 *
 *   2. THE RANK CLAIMED vs THE RANK GRANTED. Rank 1 is the local antibiogram and
 *      it OUTRANKS the national guidelines, so a form that silently accepted a
 *      claimed rank would let any PDF overrule ICMR.
 *
 *   3. THE MARKDOWN. Everything downstream — the chunks, the embeddings, the
 *      citations a clinician is later shown — is derived from it. Without it,
 *      "the system indexed my antibiogram correctly" is something a user can only
 *      take on trust.
 */

const RANK_OPTIONS = [
  { value: "", label: "No claim — hold for reference only (rank 4)" },
  { value: "1", label: "Rank 1 — local institutional antibiogram or formulary" },
  { value: "2", label: "Rank 2 — national guideline" },
  { value: "3", label: "Rank 3 — international guideline" },
];

const OPTIMISTIC_SEQUENCE = [
  ["INGEST_RECEIVE"],
  ["INGEST_CONVERT", "INGEST_EXTRACT"],
  ["INGEST_VALIDATE", "INGEST_REVIEW"],
  ["INGEST_CLASSIFY", "INGEST_CHUNK"],
  ["INGEST_EMBED", "INGEST_RETURN"],
];

type Check = { rule_id: string; name: string; passed: boolean; severity: string; detail: string };

type Outcome = {
  accepted: boolean;
  document_id: string | null;
  granted_precedence_rank: number;
  claimed_precedence_rank: number | null;
  rank_downgraded: boolean;
  clinical_domain: string;
  chunks_added: number;
  reason: string;
  agent_classification: string | null;
  agent_reason: string | null;
  classified_by_model: boolean;
  notes: string[];
  file_sha256: string | null;
  conversion: {
    converter?: string;
    characters?: number;
    pages?: number | null;
    headings_detected?: number;
    tables_detected?: number;
    truncated_at_page?: number | null;
    notes?: string[];
  };
  validation: {
    passed: boolean;
    checks: Check[];
    checks_passed: number;
    checks_run: number;
    blocking_failures: string[];
    warnings: string[];
    reviewed_by_model: boolean;
    model: string | null;
    model_confidence: number;
    document_kind: string | null;
    concerns: string[];
  } | null;
  markdown_preview: string;
  markdown_truncated: boolean;
  markdown_characters: number;
  markdown_url: string | null;
  trace: Trace | null;
};

export default function IngestionAgentPanel({
  graph,
  status,
}: {
  graph: FlowGraph | null;
  status: { ingestion_validation_requires_model?: boolean } | null;
}) {
  const { token, doctor } = useAuth();

  const [file, setFile] = useState<File | null>(null);
  const [documentId, setDocumentId] = useState("");
  const [title, setTitle] = useState("");
  const [issuingOrg, setIssuingOrg] = useState("");
  const [claimedRank, setClaimedRank] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState("");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [library, setLibrary] = useState<any[]>([]);

  async function loadLibrary() {
    try {
      const res = await fetch("/api/agents/documents");
      if (res.ok) setLibrary((await res.json()).documents ?? []);
    } catch {
      /* the library is context, not the task; a failure here is not worth an alert */
    }
  }

  useEffect(() => {
    loadLibrary();
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !documentId.trim() || !title.trim() || busy) return;

    setBusy(true);
    setError("");
    setOutcome(null);
    setStage(0);

    const ticker = window.setInterval(
      () => setStage((s) => Math.min(s + 1, OPTIMISTIC_SEQUENCE.length - 1)),
      1200,
    );

    const body = new FormData();
    body.append("file", file);
    body.append("document_id", documentId.trim().toUpperCase());
    body.append("title", title.trim());
    body.append("issuing_org", issuingOrg.trim());
    if (claimedRank) body.append("claimed_rank", claimedRank);

    try {
      const res = await fetch("/api/agents/upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body,
      });
      const data = await res.json();

      // A 422 carries the WHOLE outcome, not just a message: a refusal here is
      // the guardrails working, and the reader needs the failed checks and the
      // trace to see which rule stopped it.
      if (res.status === 422 && data?.validation) {
        setOutcome(data);
      } else if (!res.ok) {
        throw new Error(data?.detail || data?.reason || "The document could not be ingested.");
      } else {
        setOutcome(data);
        setFile(null);
        setDocumentId("");
        setTitle("");
        setIssuingOrg("");
        setClaimedRank("");
        loadLibrary();
      }
    } catch (err: any) {
      setError(err?.message || "Upload failed.");
    } finally {
      window.clearInterval(ticker);
      setBusy(false);
    }
  }

  const validation = outcome?.validation;
  const conversion = outcome?.conversion ?? {};
  const canAttestRankOne = ["ATTENDING_PHYSICIAN", "INFECTIOUS_DISEASE_SPECIALIST", "CLINICAL_PHARMACIST"]
    .includes(doctor?.clinician_role ?? "");

  return (
    <div style={{ display: "grid", gap: "18px" }}>
      <AgentFlowGraph
        graph={graph}
        trace={outcome?.trace ?? null}
        running={busy ? OPTIMISTIC_SEQUENCE[stage] : []}
        busy={busy}
      />

      {/* ------------------------------------------------------------- upload */}
      <section className="info-section" style={{ background: "#ffffff", padding: "22px 25px" }}>
        <div className="section-title-row" style={{ marginBottom: "12px" }}>
          <div>
            <p className="dashboard-kicker">RUN THE INGESTION AGENT</p>
            <h2>Add a document to the vector database</h2>
          </div>
          <Upload size={22} color="#2d7064" />
        </div>

        <p style={{ color: "#607371", fontSize: "0.85rem", margin: "0 0 16px", lineHeight: 1.6, maxWidth: "88ch" }}>
          A hospital antibiogram, local formulary or departmental protocol is converted to Markdown,
          checked against the guardrails, ranked, chunked and embedded. It becomes searchable by the
          evidence agent and by RAG chat the moment it is indexed. The rank you claim is a{" "}
          <strong>request</strong>, not a setting, and the system states which rank it granted and why.
        </p>

        <form onSubmit={submit} style={{ display: "grid", gap: "12px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "12px" }}>
            <div>
              <label className="field-label">Document ID *</label>
              <input
                className="dashboard-select"
                placeholder="e.g. LOCAL-ANTIBIOGRAM-2026"
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="field-label">Title *</label>
              <input
                className="dashboard-select"
                placeholder="e.g. Apollo Hospital Antibiogram 2026"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "12px" }}>
            <div>
              <label className="field-label">Issuing organisation</label>
              <input
                className="dashboard-select"
                placeholder="e.g. Infection Control Committee"
                value={issuingOrg}
                onChange={(e) => setIssuingOrg(e.target.value)}
              />
            </div>
            <div>
              <label className="field-label">Precedence rank claimed</label>
              <select className="dashboard-select" value={claimedRank} onChange={(e) => setClaimedRank(e.target.value)}>
                {RANK_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="field-label">File — PDF, TXT or MD (max 40 MB)</label>
            <input
              type="file"
              accept=".pdf,.txt,.md"
              className="dashboard-select"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
            />
          </div>

          {claimedRank === "1" && (
            <p className="evidence-caveat" style={{ margin: 0 }}>
              <ShieldAlert size={13} style={{ verticalAlign: "-2px", marginRight: "5px" }} />
              Rank 1 outranks the national guidelines. It is granted only if your session role can
              attest it <em>and</em> the agent's own reading of the document agrees.{" "}
              {canAttestRankOne
                ? `Your role (${doctor?.clinician_role}) can attest it.`
                : `Your role (${doctor?.clinician_role ?? "unknown"}) cannot attest it, so this will be held at reference-only rank.`}
            </p>
          )}

          {status?.ingestion_validation_requires_model && (
            <p className="evidence-caveat" style={{ margin: 0 }}>
              Strict validation is on: a document is refused unless a model actually reviews its
              content.
            </p>
          )}

          <div>
            <button className="dashboard-button primary" type="submit" disabled={busy || !file}>
              <Upload size={15} /> {busy ? "Converting, validating, indexing…" : "Run ingestion pipeline"}
            </button>
          </div>
        </form>

        {error && (
          <div className="form-error" style={{ marginTop: "14px", borderRadius: "4px" }}>
            <strong>Not ingested.</strong> {error}
          </div>
        )}
      </section>

      {/* --------------------------------------------------------- validation */}
      {validation && (
        <section className="info-section" style={{ background: "#ffffff", padding: "22px 25px" }}>
          <div className="section-title-row" style={{ marginBottom: "10px" }}>
            <div>
              <p className="dashboard-kicker">GUARDRAILS</p>
              <h2>
                {outcome?.accepted ? "Validation passed" : "Refused by validation"}
              </h2>
            </div>
            <span className={`flow-badge ${validation.passed ? "ok" : "refused"}`}>
              {validation.checks_passed}/{validation.checks_run} checks passed
            </span>
          </div>

          <p style={{ fontSize: "0.78rem", color: "#718281", margin: "0 0 14px", lineHeight: 1.55 }}>
            Deterministic rules run first and a blocking failure ends the pipeline before any model
            is consulted. The model review that follows may only <strong>reject</strong> — it can
            never clear a document a rule blocked, and never raises a document's standing.
            {validation.reviewed_by_model
              ? ` Reviewed by ${validation.model} at confidence ${validation.model_confidence}.`
              : " No model reviewed this document's content."}
          </p>

          <div style={{ display: "grid", gap: "7px" }}>
            {validation.checks.map((c) => (
              <div
                key={c.rule_id}
                className={`check-row${
                  c.passed ? "" : c.severity === "BLOCKING" ? " is-failed" : " is-warning"
                }`}
              >
                {c.passed ? (
                  <CheckCircle2 size={15} color="#2d7064" style={{ flexShrink: 0, marginTop: "1px" }} />
                ) : c.severity === "BLOCKING" ? (
                  <XCircle size={15} color="#a33d31" style={{ flexShrink: 0, marginTop: "1px" }} />
                ) : (
                  <AlertTriangle size={15} color="#a65e38" style={{ flexShrink: 0, marginTop: "1px" }} />
                )}
                <code>{c.rule_id}</code>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <strong style={{ color: "#173c3d", fontSize: "0.78rem" }}>{c.name}</strong>
                  <p style={{ margin: "3px 0 0", color: "#526968" }}>{c.detail}</p>
                </div>
              </div>
            ))}
          </div>

          {validation.concerns.length > 0 && (
            <div style={{ marginTop: "12px" }}>
              <p className="dashboard-kicker" style={{ marginBottom: "6px" }}>MODEL CONCERNS</p>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "0.79rem", color: "#526968", lineHeight: 1.6 }}>
                {validation.concerns.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          )}
        </section>
      )}

      {/* ------------------------------------------------------------ outcome */}
      {outcome?.accepted && (
        <section className="info-section" style={{ background: "#ffffff", padding: "22px 25px" }}>
          <div className="section-title-row" style={{ marginBottom: "12px" }}>
            <div>
              <p className="dashboard-kicker">INDEXED</p>
              <h2>{outcome.document_id}</h2>
            </div>
            <span className={`flow-badge ${outcome.rank_downgraded ? "degraded" : "ok"}`}>
              {outcome.rank_downgraded ? "granted a lower rank than claimed" : "ingested"}
            </span>
          </div>

          <ul className="flow-metrics" style={{ marginTop: 0, marginBottom: "14px" }}>
            <li>rank claimed <b>{outcome.claimed_precedence_rank ?? "none"}</b></li>
            <li>rank granted <b>{outcome.granted_precedence_rank}</b></li>
            <li>read as <b>{outcome.agent_classification ?? "—"}</b></li>
            <li>by model <b>{outcome.classified_by_model ? "yes" : "no"}</b></li>
            <li>chunks indexed <b>{outcome.chunks_added}</b></li>
            <li>pages <b>{conversion.pages ?? "n/a"}</b></li>
            <li>headings <b>{conversion.headings_detected ?? 0}</b></li>
            <li>tables <b>{conversion.tables_detected ?? 0}</b></li>
          </ul>

          {outcome.agent_reason && (
            <p style={{ fontSize: "0.82rem", color: "#526968", margin: "0 0 10px" }}>
              <FileText size={12} style={{ verticalAlign: "-1px", marginRight: "5px" }} />
              {outcome.agent_reason}
            </p>
          )}

          {/* The reason a rank was refused is the safety behaviour. Never collapsed. */}
          {outcome.notes?.map((n, i) => (
            <p key={i} className="evidence-caveat">{n}</p>
          ))}

          {conversion.truncated_at_page && (
            <p className="evidence-caveat">
              Only the first {conversion.truncated_at_page} pages were converted. The rest of the
              document is not in the index — raise <code>MARKDOWN_MAX_PAGES</code> to ingest it all.
            </p>
          )}

          <p style={{ fontSize: "0.75rem", color: "#718281", margin: "8px 0 0", lineHeight: 1.55 }}>
            Recorded as a clinician upload and not verified against any published copy. Source
            SHA-256 <code style={{ fontSize: "0.72rem" }}>{outcome.file_sha256?.slice(0, 24)}…</code>
          </p>
        </section>
      )}

      {/* ----------------------------------------------------------- markdown */}
      {outcome?.markdown_preview && (
        <section className="info-section" style={{ background: "#ffffff", padding: "22px 25px" }}>
          <div className="section-title-row" style={{ marginBottom: "10px" }}>
            <div>
              <p className="dashboard-kicker">CONVERTED MARKDOWN</p>
              <h2>What was actually indexed</h2>
            </div>
            {outcome.markdown_url && (
              <a
                className="dashboard-button primary"
                href={`${outcome.markdown_url}?download=true`}
                download={`${outcome.document_id}.md`}
              >
                <Download size={15} /> Download .md
              </a>
            )}
          </div>

          <p style={{ fontSize: "0.78rem", color: "#718281", margin: "0 0 12px", lineHeight: 1.55 }}>
            Every chunk, embedding and citation downstream is derived from this text. Read it
            against the original to check that what the corpus holds is what the document said.
            Structure markers and extraction repair are the only additions — nothing is paraphrased.
            {outcome.markdown_truncated &&
              ` Showing the first ${outcome.markdown_preview.length.toLocaleString()} of ${outcome.markdown_characters.toLocaleString()} characters.`}
          </p>

          <div className="markdown-preview">{outcome.markdown_preview}</div>
        </section>
      )}

      {/* ------------------------------------------------------------ library */}
      {library.length > 0 && (
        <section className="info-section" style={{ background: "#ffffff", padding: "22px 25px" }}>
          <div className="section-title-row" style={{ marginBottom: "12px" }}>
            <div>
              <p className="dashboard-kicker">INGESTED THROUGH THIS PIPELINE</p>
              <h2>{library.length} document{library.length === 1 ? "" : "s"} with Markdown held</h2>
            </div>
          </div>

          <div style={{ display: "grid", gap: "8px" }}>
            {library.map((d) => (
              <div key={d.document_id} className="verdict-row">
                <FileText size={15} color="#2d7064" style={{ flexShrink: 0, marginTop: "2px" }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", gap: "8px", alignItems: "baseline", flexWrap: "wrap" }}>
                    <strong style={{ color: "#173c3d", fontSize: "0.78rem" }}>{d.document_id}</strong>
                    <span className="flow-badge pending">rank {d.precedence_rank ?? "—"}</span>
                    {!d.still_indexed && <span className="flow-badge skipped">no longer indexed</span>}
                  </div>
                  <p style={{ margin: "3px 0 0", color: "#526968" }}>
                    {d.title ?? "Title not recorded"}
                    {d.issuing_org ? ` — ${d.issuing_org}` : ""}
                  </p>
                </div>
                <a
                  href={`${d.markdown_url}?download=true`}
                  download={`${d.document_id}.md`}
                  style={{ color: "#2d7064", fontSize: "0.74rem", fontWeight: 700, whiteSpace: "nowrap" }}
                >
                  <Download size={12} style={{ verticalAlign: "-2px" }} /> .md
                </a>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
