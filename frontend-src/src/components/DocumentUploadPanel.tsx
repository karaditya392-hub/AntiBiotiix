import { useState } from "react";
import { Upload, ShieldAlert, CheckCircle2, FileText } from "lucide-react";

/**
 * Agent 1 — clinician document ingestion.
 *
 * A clinician uploads a trusted document (a hospital antibiogram, a local
 * formulary, a departmental protocol) and it becomes retrievable evidence
 * alongside the national corpus.
 *
 * THE PART OF THIS UI THAT MATTERS IS NOT THE FILE PICKER. It is the result
 * panel: the rank the uploader ASKED for and the rank the system GRANTED are
 * shown separately, with the reason whenever they differ. Rank 1 is the local
 * antibiogram, which outranks the national guidelines — so an upload form that
 * silently accepted a claimed rank would let any PDF overrule ICMR. The refusal
 * is the feature, and it has to be visible.
 */

const RANK_OPTIONS = [
  { value: "", label: "No claim — hold for reference only (rank 4)" },
  { value: "1", label: "Rank 1 — local institutional antibiogram or formulary" },
  { value: "2", label: "Rank 2 — national guideline" },
  { value: "3", label: "Rank 3 — international guideline" },
];

export default function DocumentUploadPanel({ token }: { token: string | null }) {
  const [file, setFile] = useState<File | null>(null);
  const [documentId, setDocumentId] = useState("");
  const [title, setTitle] = useState("");
  const [issuingOrg, setIssuingOrg] = useState("");
  const [claimedRank, setClaimedRank] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<any>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !documentId.trim() || !title.trim()) return;
    setBusy(true);
    setError("");
    setResult(null);

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
      if (!res.ok) throw new Error(data.detail || "The document could not be ingested.");
      setResult(data);
      setFile(null);
      setDocumentId("");
      setTitle("");
      setIssuingOrg("");
      setClaimedRank("");
    } catch (err: any) {
      setError(err.message || "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  const downgraded = result?.rank_downgraded;

  return (
    <section className="info-section" style={{ background: "#ffffff", padding: "24px" }}>
      <div className="section-title-row" style={{ marginBottom: "12px" }}>
        <div>
          <p className="dashboard-kicker">ADD A TRUSTED DOCUMENT</p>
          <h2>Upload to the Retrieval Corpus</h2>
        </div>
        <Upload size={22} color="#2d7064" />
      </div>

      <p style={{ color: "#607371", fontSize: "0.85rem", margin: "0 0 16px" }}>
        A hospital antibiogram, local formulary or departmental protocol becomes retrievable
        evidence alongside the national guidelines. The document is read, classified and ranked;
        the rank you claim is a <strong>request</strong>, not a setting, and the system states
        which rank it granted and why.
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
            <select
              className="dashboard-select"
              value={claimedRank}
              onChange={(e) => setClaimedRank(e.target.value)}
            >
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
          <p style={{ fontSize: "0.78rem", color: "#8a4b1f", background: "#fdf3e3",
                      border: "1px solid #e0c9a0", borderRadius: "4px", padding: "9px 11px", margin: 0 }}>
            <ShieldAlert size={13} style={{ verticalAlign: "-2px", marginRight: "5px" }} />
            Rank 1 outranks the national guidelines. It is granted only if your session role can
            attest it <em>and</em> the system&rsquo;s own reading of the document agrees. Otherwise it is
            held at reference-only rank, and you will be told why.
          </p>
        )}

        <div>
          <button className="dashboard-button primary" type="submit" disabled={busy || !file}>
            <Upload size={15} /> {busy ? "Reading and classifying..." : "Ingest Document"}
          </button>
        </div>
      </form>

      {error && (
        <div style={{ marginTop: "14px", background: "#fbe9e5", border: "1px solid #e0b4ac",
                      borderRadius: "6px", padding: "13px", color: "#a33d31", fontSize: "0.86rem" }}>
          <strong>Not ingested.</strong> {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: "16px", border: "1px solid #cbd9d4", borderRadius: "6px", overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between",
                        alignItems: "center", flexWrap: "wrap", gap: "8px",
                        background: downgraded ? "#fdf3e3" : "#eef6f2",
                        borderBottom: `2px solid ${downgraded ? "#a65e38" : "#2d7064"}` }}>
            <strong style={{ color: "#173c3d", fontSize: "0.9rem" }}>
              {downgraded
                ? <><ShieldAlert size={14} style={{ verticalAlign: "-2px" }} /> Ingested at a lower rank than claimed</>
                : <><CheckCircle2 size={14} style={{ verticalAlign: "-2px" }} /> Ingested</>}
            </strong>
            <span style={{ fontFamily: "monospace", fontSize: "0.74rem", color: "#607371" }}>
              {result.document_id} · {result.chunks_added} passages
            </span>
          </div>

          <div style={{ padding: "14px", display: "grid", gap: "10px" }}>
            <div style={{ display: "flex", gap: "22px", flexWrap: "wrap", fontSize: "0.82rem" }}>
              <span style={{ color: "#607371" }}>
                Rank claimed: <strong style={{ color: "#173c3d" }}>
                  {result.claimed_precedence_rank ?? "none"}
                </strong>
              </span>
              <span style={{ color: "#607371" }}>
                Rank granted: <strong style={{ color: downgraded ? "#a65e38" : "#2d7064" }}>
                  {result.granted_precedence_rank}
                </strong>
              </span>
              <span style={{ color: "#607371" }}>
                Read as: <strong style={{ color: "#173c3d" }}>{result.agent_classification}</strong>
              </span>
              <span style={{ color: "#607371" }}>
                Classified by model: <strong style={{ color: "#173c3d" }}>
                  {result.classified_by_model ? "yes" : "no"}
                </strong>
              </span>
            </div>

            {result.agent_reason && (
              <p style={{ fontSize: "0.83rem", color: "#526968", margin: 0 }}>
                <FileText size={12} style={{ verticalAlign: "-1px", marginRight: "5px" }} />
                {result.agent_reason}
              </p>
            )}

            {/* The reason a rank was refused. This is the safety behaviour, so it is
                never collapsed or abbreviated. */}
            {result.notes?.map((n: string, i: number) => (
              <p key={i} style={{ fontSize: "0.82rem", color: "#8a4b1f", background: "#fdf6ef",
                                  border: "1px solid #e0c9a0", borderRadius: "4px",
                                  padding: "9px 11px", margin: 0 }}>
                {n}
              </p>
            ))}

            <p style={{ fontSize: "0.75rem", color: "#718281", margin: 0 }}>
              Recorded as a clinician upload, not verified against any published copy. It is
              retrievable immediately and carries its provenance on every passage.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
