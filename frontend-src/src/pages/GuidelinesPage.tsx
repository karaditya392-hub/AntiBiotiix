import { useEffect, useState } from "react";
import { ShieldAlert, CheckCircle2, RotateCcw, FileCheck, X } from "lucide-react";
import ClinicalToolsLayout from "@/components/ClinicalToolsLayout";
import "@/styles/patient-dashboard.css";

export default function GuidelinesPage() {
  const [rules, setRules] = useState<any[]>([]);
  const [governance, setGovernance] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("ALL");

  // Review / Sign Off Modal state
  const [activeReviewRule, setActiveReviewRule] = useState<any>(null);
  const [reviewAction, setReviewAction] = useState("APPROVED");
  const [reviewRationale, setReviewRationale] = useState("");
  const [reviewError, setReviewError] = useState("");
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewSuccessMsg, setReviewSuccessMsg] = useState("");
  const [corpus, setCorpus] = useState<any>(null);

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [rulesRes, govRes, healthRes] = await Promise.all([
        fetch("/api/guidelines/rules"),
        fetch("/api/rules/governance"),
        // Corpus size is read from the system, never typed into the page: the old
        // hardcoded passage count was wrong the first time a document was ingested.
        fetch("/api/system/health"),
      ]);
      if (healthRes.ok) {
        setCorpus((await healthRes.json())?.guideline_corpus ?? null);
      }

      if (rulesRes.ok) {
        const rulesData = await rulesRes.json();
        setRules(rulesData.rules || []);
      } else {
        throw new Error("Guidelines service unavailable");
      }

      if (govRes.ok) {
        const govData = await govRes.json();
        setGovernance(govData.rules || []);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load clinical guidelines.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function handleConfirmReview(e: React.FormEvent) {
    e.preventDefault();
    setReviewError("");
    setReviewSuccessMsg("");
    if (!reviewRationale.trim() || reviewRationale.trim().length < 10) {
      setReviewError("A substantive clinical rationale (minimum 10 characters) is required to record a governance decision.");
      return;
    }
    setReviewSubmitting(true);

    try {
      const login = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "CLINICIAN-DEMO", role: "ATTENDING_PHYSICIAN" }),
      });
      const auth = await login.json();

      const res = await fetch(`/api/rules/${encodeURIComponent(activeReviewRule.rule_id)}/review`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${auth.access_token}`,
        },
        body: JSON.stringify({
          action: reviewAction.trim().toUpperCase(),
          rationale: reviewRationale.trim(),
        }),
      });

      if (res.ok) {
        setReviewSuccessMsg(`Governance review recorded successfully for ${activeReviewRule.rule_id}.`);
        await loadData();
        setTimeout(() => {
          setActiveReviewRule(null);
          setReviewRationale("");
          setReviewSuccessMsg("");
        }, 1200);
      } else {
        const errData = await res.json();
        setReviewError(errData.detail || "Failed to record rule review decision.");
      }
    } catch {
      setReviewError("An error occurred during review submission.");
    } finally {
      setReviewSubmitting(false);
    }
  }

  const categories = ["ALL", ...Array.from(new Set(rules.map((r) => r.category))).sort()];

  const filteredRules = rules.filter((r) => {
    const matchesCat = selectedCategory === "ALL" || r.category === selectedCategory;
    const q = query.trim().toLowerCase();
    if (!q) return matchesCat;
    return (
      matchesCat &&
      (r.rule_id.toLowerCase().includes(q) ||
        r.rule_name.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.output_concern.toLowerCase().includes(q) ||
        r.recommendation.toLowerCase().includes(q) ||
        r.evidence_source.toLowerCase().includes(q))
    );
  });

  return (
    <ClinicalToolsLayout>
      <section className="info-section" style={{ background: "#ffffff", padding: "24px" }}>
        <div className="section-title-row" style={{ marginBottom: "16px" }}>
          <div>
            <p className="dashboard-kicker">
              {corpus?.chunks
                ? `${corpus.chunks.toLocaleString()} INDEXED PASSAGES ACROSS ${corpus.documents} DOCUMENTS & CATALOG`
                : "INDEXED GUIDELINE PASSAGES & CATALOG"}
            </p>
            <h2>Clinical Guidelines & Rules Explorer</h2>
          </div>
          <button className="dashboard-button secondary" onClick={loadData}>
            <RotateCcw size={14} /> Refresh Catalog
          </button>
        </div>

        {/* SEARCH & FILTER CONTROLS */}
        <div style={{ display: "flex", gap: "12px", marginBottom: "20px", flexWrap: "wrap" }}>
          <div style={{ flex: 2, minWidth: "240px" }}>
            <label className="field-label">Search Rules & Guidelines</label>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                type="text"
                placeholder="Search rule ID, syndrome, medication, or recommendation..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="dashboard-select"
              />
            </div>
          </div>

          <div style={{ flex: 1, minWidth: "180px" }}>
            <label className="field-label">Filter Category</label>
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="dashboard-select"
            >
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* LOADING & ERROR HANDLING */}
        {loading ? (
          <div className="dashboard-empty">Loading guideline catalog and rules...</div>
        ) : error ? (
          <div className="dashboard-empty">
            <ShieldAlert size={28} color="#a33d31" />
            <h2>This clinical tool is currently unavailable</h2>
            <p>{error}</p>
            <button className="dashboard-button primary" onClick={loadData}>
              Retry
            </button>
          </div>
        ) : (
          <div>
            <p className="muted" style={{ marginBottom: "14px" }}>
              Showing {filteredRules.length} of {rules.length} catalog rules. Clinicians can review and record governance sign-offs for each entry.
            </p>

            <div style={{ display: "grid", gap: "16px" }}>
              {filteredRules.map((rule) => {
                const gov = governance.find((g) => g.rule_id === rule.rule_id);
                const effectiveStatus = (gov?.effective_status || rule.approval_status || "PENDING_CLINICAL_REVIEW").replace(/_/g, " ");
                const severityColor =
                  rule.severity === "CRITICAL" ? "#a33d31" : rule.severity === "HIGH" ? "#c86d38" : "#2d7064";

                const isFinalApproved = gov?.effective_status === "APPROVED_FOR_CLINICAL_USE" || gov?.last_action === "APPROVED";

                return (
                  <article
                    key={rule.rule_id}
                    style={{
                      background: "#fbfcf9",
                      border: "1px solid #cbd9d4",
                      borderLeft: `5px solid ${severityColor}`,
                      borderRadius: "6px",
                      padding: "18px",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                      <div>
                        <span style={{ background: severityColor, color: "#fff", padding: "3px 8px", borderRadius: "3px", fontSize: "0.72rem", fontWeight: 700 }}>
                          {rule.severity}
                        </span>
                        <span style={{ background: "#eef6f2", color: "#173c3d", padding: "3px 8px", borderRadius: "3px", fontSize: "0.72rem", fontWeight: 700, marginLeft: "6px" }}>
                          {rule.category}
                        </span>
                        <h3 style={{ margin: "6px 0 2px", fontSize: "1.1rem", color: "#173c3d", fontFamily: "Space Grotesk, sans-serif" }}>
                          {rule.rule_id}: {rule.rule_name}
                        </h3>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <span
                          style={{
                            fontSize: "0.72rem",
                            color: isFinalApproved ? "#173c3d" : "#718281",
                            background: isFinalApproved ? "#e4f0e9" : "#f0f4f2",
                            padding: "4px 8px",
                            borderRadius: "4px",
                            fontWeight: 700,
                            display: "flex",
                            alignItems: "center",
                            gap: "4px",
                          }}
                        >
                          <CheckCircle2 size={13} color={isFinalApproved ? "#2d7064" : "#718281"} />
                          {effectiveStatus}
                        </span>

                        <button
                          className="dashboard-button secondary"
                          style={{ padding: "6px 12px", fontSize: "0.75rem" }}
                          onClick={() => {
                            setActiveReviewRule(rule);
                            setReviewAction("APPROVED");
                            setReviewRationale("");
                            setReviewError("");
                            setReviewSuccessMsg("");
                          }}
                        >
                          <FileCheck size={14} /> Review & Sign Off
                        </button>
                      </div>
                    </div>

                    <p style={{ margin: "6px 0", fontSize: "0.86rem", color: "#203236" }}>
                      <b>Output Concern:</b> {rule.output_concern}
                    </p>

                    <p style={{ margin: "6px 0", fontSize: "0.86rem", color: "#173c3d", fontWeight: 600 }}>
                      <b>Clinical Recommendation:</b> {rule.recommendation}
                    </p>

                    <div style={{ background: "#f0f6f1", border: "1px solid #d0e2d8", padding: "10px 12px", borderRadius: "4px", marginTop: "10px", fontSize: "0.78rem" }}>
                      <div><b>Evidence Source:</b> {rule.evidence_source} ({rule.guideline_version})</div>
                      {rule.section_page && <div><b>Citation Page:</b> {rule.section_page}</div>}
                      <div><b>Rule Author:</b> {rule.author || "SYSTEM_GENERATED"}</div>
                      {gov?.reviewed_by && (
                        <div style={{ marginTop: "4px", color: "#2d7064", fontWeight: 600 }}>
                          Reviewed by: {gov.reviewed_by} ({gov.reviewer_role || "ATTENDING_PHYSICIAN"}) · Rationale: "{gov.review_rationale || "Clinical validation verified."}"
                        </div>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* CLINICIAN GOVERNANCE REVIEW & APPROVAL MODAL */}
      {activeReviewRule && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <h3 style={{ margin: 0, color: "#173c3d" }}>Record Clinical Governance Review</h3>
              <X size={18} style={{ cursor: "pointer" }} onClick={() => setActiveReviewRule(null)} />
            </div>

            <p style={{ fontSize: "0.84rem", color: "#526968", marginBottom: "14px" }}>
              Rule: <strong>{activeReviewRule.rule_id}</strong> — {activeReviewRule.rule_name}
            </p>

            <form onSubmit={handleConfirmReview} style={{ display: "grid", gap: "12px" }}>
              <div>
                <label className="field-label">Review Action *</label>
                <select
                  value={reviewAction}
                  onChange={(e) => setReviewAction(e.target.value)}
                  className="dashboard-select"
                >
                  <option value="APPROVED">APPROVED (Approve for Clinical Use)</option>
                  <option value="CHANGES_REQUESTED">CHANGES_REQUESTED (Request Revision)</option>
                  <option value="REJECTED">REJECTED (Reject Rule)</option>
                  <option value="RETIRED">RETIRED (Retire Rule)</option>
                </select>
              </div>

              <div>
                <label className="field-label">Substantive Clinical Rationale *</label>
                <textarea
                  rows={3}
                  placeholder="Enter clinical review rationale (minimum 10 characters)..."
                  value={reviewRationale}
                  onChange={(e) => setReviewRationale(e.target.value)}
                  className="dashboard-select"
                  required
                />
                <p className="muted" style={{ fontSize: "0.72rem", marginTop: "4px" }}>
                  Your governance sign-off and rationale will be permanently recorded in the immutable SHA-256 audit trail.
                </p>
              </div>

              {reviewError && <p className="form-error">{reviewError}</p>}
              {reviewSuccessMsg && <p className="form-intro" style={{ color: "#2d7064", fontWeight: 700 }}>{reviewSuccessMsg}</p>}

              <div style={{ marginTop: "12px", display: "flex", gap: "10px", justifyContent: "flex-end" }}>
                <button type="button" className="dashboard-button secondary" onClick={() => setActiveReviewRule(null)}>
                  Cancel
                </button>
                <button type="submit" className="dashboard-button primary" disabled={reviewSubmitting}>
                  {reviewSubmitting ? "Recording..." : "Record Governance Decision"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </ClinicalToolsLayout>
  );
}
