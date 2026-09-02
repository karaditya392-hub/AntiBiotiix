import { useEffect, useState } from "react";
import { ShieldAlert, CheckCircle2, RotateCcw, FileCheck, X, Layers, ChevronRight } from "lucide-react";
import ClinicalToolsLayout from "@/components/ClinicalToolsLayout";
import DocumentUploadPanel from "@/components/DocumentUploadPanel";
import { useAuth } from "@/context/AuthContext";
import "@/styles/patient-dashboard.css";

export default function GuidelinesPage() {
  // The upload's attesting role is resolved server-side from THIS token, which is
  // why the panel takes the session token rather than logging in on its own: a
  // rank-1 claim has to be attributable to the clinician actually signed in.
  const { token } = useAuth();
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

  // Held documents, and which domain the reader has opened.
  //
  // The composition strip used to be seven static labels. They read as tabs -- they
  // are a row of counts, so of course they do -- and clicking one did nothing,
  // because nothing in the app listed the documents behind a count at all. The
  // counts were auditable only in the sense that you could be told a number.
  const [documents, setDocuments] = useState<any[]>([]);
  const [openDomain, setOpenDomain] = useState<string | null>(null);
  const [openDoc, setOpenDoc] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [rulesRes, govRes, healthRes, docsRes] = await Promise.all([
        fetch("/api/guidelines/rules"),
        fetch("/api/rules/governance"),
        // Corpus size is read from the system, never typed into the page: the old
        // hardcoded passage count was wrong the first time a document was ingested.
        fetch("/api/system/health"),
        // The documents behind the counts. Without this the composition strip can
        // only ever report a number nobody can check.
        fetch("/api/guidelines/documents"),
      ]);
      if (healthRes.ok) {
        setCorpus((await healthRes.json())?.guideline_corpus ?? null);
      }
      if (docsRes.ok) {
        setDocuments((await docsRes.json())?.documents ?? []);
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
        // Searchable because it is now visible on the card.
        (r.input_conditions || "").toLowerCase().includes(q) ||
        // evidence_source already contains the unverified authorities by name, so
        // searching "AAAAI" still finds the rules that cite it.
        r.evidence_source.toLowerCase().includes(q))
    );
  });

  return (
    <ClinicalToolsLayout>
      <DocumentUploadPanel token={token} />

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

        {/*
          CORPUS COMPOSITION.

          The document count above is the number most likely to be misread. Only a
          fraction of the corpus carries antimicrobial authority; the rest is
          condition-specific clinical guidance, research ethics, laboratory and
          programme policy. Showing the count without the breakdown invites a reader
          to treat all of it as prescribing evidence, so the breakdown sits next to
          the count rather than behind a link.
        */}
        {corpus?.documents_by_clinical_domain && (
          <div
            style={{
              background: "#f0f6f1",
              border: "1px solid #d0e2d8",
              borderRadius: "6px",
              padding: "12px 14px",
              marginBottom: "18px",
              fontSize: "0.78rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
              <Layers size={14} color="#2d7064" />
              <strong style={{ color: "#173c3d" }}>Corpus composition</strong>
              <span className="muted" style={{ fontSize: "0.72rem", fontWeight: 400 }}>
                — select a domain to list the documents it holds
              </span>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "8px" }}>
              {Object.entries(corpus.documents_by_clinical_domain as Record<string, number>)
                .sort((a, b) => b[1] - a[1])
                .map(([domain, count]) => {
                  const isOpen = openDomain === domain;
                  return (
                    <button
                      key={domain}
                      title={`${domain} - click to list these ${count} document(s)`}
                      onClick={() => {
                        setOpenDomain(isOpen ? null : domain);
                        // Collapsing a domain and reopening another should not leave
                        // a document from the previous one expanded.
                        setOpenDoc(null);
                      }}
                      style={{
                        background: isOpen ? "#2d7064" : "#ffffff",
                        color: isOpen ? "#ffffff" : "#526968",
                        border: `1px solid ${isOpen ? "#2d7064" : "#cbd9d4"}`,
                        borderRadius: "3px",
                        padding: "4px 9px",
                        fontWeight: 600,
                        fontSize: "0.72rem",
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "5px",
                      }}
                    >
                      {count} {domain.replace(/_/g, " ").toLowerCase()}
                      <ChevronRight
                        size={12}
                        style={{
                          transform: isOpen ? "rotate(90deg)" : "none",
                          transition: "transform 120ms",
                        }}
                      />
                    </button>
                  );
                })}
            </div>

            {/* The documents behind the count the reader just clicked. */}
            {openDomain && (
              <div style={{ marginTop: "10px", borderTop: "1px solid #d0e2d8", paddingTop: "10px" }}>
                {(() => {
                  const inDomain = documents.filter((d) => d.clinical_domain === openDomain);
                  const caveat = inDomain[0]?.domain_caveat;
                  return (
                    <>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                        <strong style={{ color: "#173c3d", fontSize: "0.78rem" }}>
                          {inDomain.length} document{inDomain.length === 1 ? "" : "s"} ·{" "}
                          {openDomain.replace(/_/g, " ").toLowerCase()}
                        </strong>
                        <button
                          className="dashboard-button secondary"
                          style={{ padding: "3px 9px", fontSize: "0.7rem" }}
                          onClick={() => setOpenDomain(null)}
                        >
                          <X size={12} /> Close
                        </button>
                      </div>

                      {/* The reading contract for this whole domain, stated once above
                          the list rather than repeated on every row. */}
                      {caveat && (
                        <p style={{ fontSize: "0.72rem", color: "#8a4b1f", background: "#fdf3e3",
                                    border: "1px solid #e0c9a0", borderRadius: "4px",
                                    padding: "6px 8px", margin: "0 0 8px", lineHeight: 1.45 }}>
                          {caveat}
                        </p>
                      )}

                      {inDomain.length === 0 ? (
                        <p className="muted" style={{ fontSize: "0.74rem", margin: 0 }}>
                          The document list could not be loaded, so these documents cannot be
                          shown. The count above comes from the corpus and is unaffected.
                        </p>
                      ) : (
                        <div style={{ maxHeight: "420px", overflowY: "auto", display: "grid", gap: "6px" }}>
                          {inDomain.map((d) => {
                            const isDocOpen = openDoc === d.document_id;
                            // A page number is only a citation if it points into the
                            // official document. A transcription's page numbers are
                            // pages of the transcript, and saying so is the whole
                            // point of carrying this field.
                            const pagesAreOfficial = d.page_reference_kind === "OFFICIAL_DOCUMENT_PAGE";
                            return (
                              <div
                                key={d.document_id}
                                style={{
                                  background: "#ffffff",
                                  border: `1px solid ${isDocOpen ? "#9dc3b4" : "#cbd9d4"}`,
                                  borderRadius: "4px",
                                  fontSize: "0.74rem",
                                }}
                              >
                                <button
                                  onClick={() => setOpenDoc(isDocOpen ? null : d.document_id)}
                                  style={{
                                    width: "100%", textAlign: "left", background: "none",
                                    border: "none", padding: "8px 10px", cursor: "pointer",
                                    font: "inherit", color: "inherit",
                                  }}
                                >
                                  <div style={{ display: "flex", justifyContent: "space-between", gap: "10px" }}>
                                    <strong style={{ color: "#173c3d", display: "flex", alignItems: "center", gap: "5px" }}>
                                      <ChevronRight
                                        size={12}
                                        style={{ flexShrink: 0, transform: isDocOpen ? "rotate(90deg)" : "none", transition: "transform 120ms" }}
                                      />
                                      {d.title || d.document_id}
                                    </strong>
                                    <code style={{ color: "#718281", fontSize: "0.68rem", whiteSpace: "nowrap" }}>
                                      {d.document_id}
                                    </code>
                                  </div>
                                  <div style={{ color: "#526968", marginTop: "3px", paddingLeft: "17px" }}>
                                    {d.issuing_org}
                                  </div>
                                  <div style={{ color: "#718281", marginTop: "3px", paddingLeft: "17px",
                                                display: "flex", flexWrap: "wrap", gap: "10px" }}>
                                    <span>Version: {d.version || "not stated"}</span>
                                    <span>Rank {d.precedence_rank}</span>
                                    {d.page_count ? <span>{d.page_count} pages</span> : null}
                                    <span>{d.chunks} passages</span>
                                    <span>{d.provenance_basis?.replace(/_/g, " ").toLowerCase()}</span>
                                    {d.carries_antimicrobial_content && (
                                      <span style={{ background: "#e4f0e9", color: "#2d7064",
                                                     border: "1px solid #b9d8c8", borderRadius: "3px",
                                                     padding: "0 6px", fontWeight: 700 }}>
                                        carries antimicrobial recommendations
                                      </span>
                                    )}
                                  </div>
                                </button>

                                {/* What this document IS, in its own recorded words.
                                    Every document carries a provenance note stating its
                                    scope, what it may and may not be cited for, and how
                                    it reached the corpus. It is the most informative
                                    thing held about each one and it was not being
                                    shown, which left the list a wall of near-identical
                                    ICMR headings. */}
                                {isDocOpen && (
                                  <div style={{ borderTop: "1px solid #e2ece7", padding: "9px 10px 10px 27px",
                                                background: "#fbfcf9" }}>
                                    {/*
                                      WHAT THE DOCUMENT IS ABOUT COMES FIRST.

                                      The provenance note below is about how to treat a
                                      citation drawn from this document -- hash verified,
                                      what it may not be cited for, what governs instead.
                                      That is necessary and it is not a description. For
                                      the 22 oncology consensus documents it is generated
                                      from one template, so opening any of them showed
                                      near-identical text and the panel could not tell a
                                      reader what THIS document covers.
                                    */}
                                    {Array.isArray(d.topics) && d.topics.length > 0 && (
                                      <div style={{ marginBottom: "10px" }}>
                                        <b style={{ color: "#173c3d" }}>What this document says</b>
                                        <div style={{ display: "grid", gap: "7px", marginTop: "6px" }}>
                                          {d.topics.map((t: any, ti: number) => (
                                            <div key={`${t.heading}-${ti}`}
                                                 style={{ borderLeft: "3px solid #b9d8c8", paddingLeft: "9px" }}>
                                              <div style={{ color: "#2d5350", fontWeight: 700, fontSize: "0.71rem" }}>
                                                {/* Some documents have no headings the ingest
                                                    matcher recognised. Their passages are labelled
                                                    for what they are rather than given an invented
                                                    heading. */}
                                                {t.heading || <span style={{ fontWeight: 400, fontStyle: "italic" }}>Opening passage</span>}
                                                {t.page ? (
                                                  <span className="muted" style={{ fontWeight: 400 }}> · p. {t.page}</span>
                                                ) : null}
                                              </div>
                                              {/* Verbatim. No summary is generated: a paraphrase of a
                                                  clinical document is a new claim about it. */}
                                              <p style={{ margin: "2px 0 0", lineHeight: 1.5, color: "#203236",
                                                          fontSize: "0.72rem" }}>
                                                “{t.excerpt}”
                                              </p>
                                            </div>
                                          ))}
                                        </div>
                                        <p className="muted" style={{ margin: "6px 0 0", fontSize: "0.68rem" }}>
                                          Passages quoted verbatim from the document. Not a summary and not
                                          its full contents: each quote is the opening of a longer passage, and
                                          where a document has no headings the ingest matcher recognised, its
                                          opening passages are shown instead.
                                        </p>
                                      </div>
                                    )}

                                    {d.provenance_note && (
                                      <div style={{ marginBottom: "9px" }}>
                                        <b style={{ color: "#173c3d" }}>How a citation from it must be treated</b>
                                        <p style={{ margin: "4px 0 0", lineHeight: 1.55, color: "#526968",
                                                    fontSize: "0.72rem" }}>
                                          {d.provenance_note}
                                        </p>
                                      </div>
                                    )}

                                    <div style={{ display: "grid", gap: "3px", color: "#526968", fontSize: "0.72rem" }}>
                                      <div><b>Published:</b> {d.publication_date || "not stated in the document"}</div>
                                      <div><b>Scope:</b> {d.geographic_scope || "not stated"}</div>
                                      <div>
                                        <b>Page references:</b>{" "}
                                        {pagesAreOfficial
                                          ? "genuine pages of this edition"
                                          : d.page_reference_kind === "NO_PAGINATION"
                                            ? "none — plain-text transcription, no page locator exists"
                                            : "pages of the TRANSCRIPT, not of the official edition"}
                                      </div>
                                      <div>
                                        <b>Standing:</b>{" "}
                                        {d.carries_antimicrobial_authority
                                          ? "antimicrobial source"
                                          : d.is_clinical_guideline
                                            ? "clinical guideline, no antimicrobial authority"
                                            : "not a clinical guideline"}
                                      </div>
                                      {d.source_url && (
                                        <div>
                                          <b>Issuer:</b>{" "}
                                          <a href={d.source_url} target="_blank" rel="noreferrer"
                                             style={{ color: "#2d7064", wordBreak: "break-all" }}>
                                            {d.source_url}
                                          </a>
                                        </div>
                                      )}
                                      {d.file_sha256 && (
                                        <div style={{ wordBreak: "break-all" }}>
                                          <b>SHA-256:</b>{" "}
                                          <code style={{ fontSize: "0.68rem" }}>{d.file_sha256}</code>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            )}
            {corpus.corpus_scope_note && (
              <p className="muted" style={{ margin: 0, fontSize: "0.74rem", lineHeight: 1.5 }}>
                {corpus.corpus_scope_note}
              </p>
            )}
          </div>
        )}

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

                    {/*
                      The catalog records more about each rule than this card used
                      to show. `description` (what the rule detects) and
                      `input_conditions` (what actually makes it fire) were both
                      already written and both omitted, which left every rule looking
                      thinner than it is and gave a reader no way to see the trigger
                      without reading the JSON.
                    */}
                    {rule.description && (
                      <p style={{ margin: "8px 0 6px", fontSize: "0.86rem", color: "#203236" }}>
                        <b>What it detects:</b> {rule.description}
                      </p>
                    )}

                    {rule.input_conditions && (
                      <p style={{ margin: "6px 0", fontSize: "0.8rem", color: "#526968" }}>
                        <b>Triggers when:</b>{" "}
                        <code style={{ background: "#eef4f1", padding: "1px 5px", borderRadius: "3px", fontSize: "0.76rem" }}>
                          {rule.input_conditions}
                        </code>
                      </p>
                    )}

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
                      {(rule.effective_date || rule.review_date) && (
                        <div>
                          <b>Effective:</b> {rule.effective_date || "not stated"}
                          {" · "}
                          <b>Next review:</b> {rule.review_date || "not stated"}
                        </div>
                      )}
                      {gov?.reviewed_by && (
                        <div style={{ marginTop: "4px", color: "#2d7064", fontWeight: 600 }}>
                          Reviewed by: {gov.reviewed_by} ({gov.reviewer_role || "ATTENDING_PHYSICIAN"}) · Rationale: "{gov.review_rationale || "Clinical validation verified."}"
                        </div>
                      )}
                    </div>

                    {/*
                      NO separate "cited without an ingested document" block here.
                      Every rule carrying unverified_sources already states the same
                      thing inside its evidence_source, which is rendered above --
                      e.g. "ICMR Treatment Guidelines ... (additional authorities
                      cited without a document in this repository: AAAAI Drug Allergy
                      Practice Parameter)". Checked across all 13 such rules before
                      this block was removed: none loses the disclosure. A second
                      copy in a full-width warning bar was duplicate text, and on a
                      catalog where 13 of 30 rules carry one it made the warning
                      colour meaningless.
                    */}
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
