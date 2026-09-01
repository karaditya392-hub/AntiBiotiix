import { useEffect, useState } from "react";
import { Search, BookOpenCheck, ShieldAlert } from "lucide-react";
import ClinicalToolsLayout from "@/components/ClinicalToolsLayout";
import "@/styles/patient-dashboard.css";

export default function EvidencePage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [corpus, setCorpus] = useState<any>(null);

  // The corpus description used to be a hardcoded passage count and source list.
  // It went stale the first time a document was ingested, so read it from the
  // system instead: what this page claims to search is now what it searches.
  useEffect(() => {
    fetch("/api/system/health")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setCorpus(d?.guideline_corpus ?? null))
      .catch(() => setCorpus(null));
  }, []);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await fetch("/api/evidence/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim(), k: 4 }),
      });

      if (!res.ok) {
        throw new Error("Ask the Evidence service is unavailable");
      }
      const data = await res.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Failed to search evidence database.");
    } finally {
      setLoading(false);
    }
  }

  const exampleQueries = [
    "What is the recommended empiric regimen for community-acquired pneumonia?",
    "What are the dosage adjustments for nitrofurantoin in renal impairment?",
    "What is the WHO AWaRe classification for meropenem?",
    "What antibiotics are recommended for acute uncomplicated cystitis in ICMR STG?",
    "What are the contraindications for ciprofloxacin in pregnancy?",
  ];

  return (
    <ClinicalToolsLayout>
      <section className="info-section" style={{ background: "#ffffff", padding: "24px" }}>
        <div className="section-title-row" style={{ marginBottom: "14px" }}>
          <div>
            <p className="dashboard-kicker">EXTRACTIVE RAG EVIDENCE SEARCH</p>
            <h2>Ask the Evidence (Guideline & Drug Label Corpus)</h2>
          </div>
          <BookOpenCheck size={24} color="#2d7064" />
        </div>

        <p style={{ color: "#607371", fontSize: "0.86rem", margin: "0 0 16px" }}>
          {corpus?.chunks
            ? `Search ${corpus.chunks.toLocaleString()} verbatim passages across ${corpus.documents} ingested guideline documents, plus DailyMed drug labels.`
            : "Search the ingested guideline corpus and DailyMed drug labels."}{" "}
          Answers are strictly extractive with score citations — no LLM generates the content.
        </p>

        {/* Held for reference but not clinical guidelines: the reader has to know
            these are in the searchable corpus before a passage from one appears. */}
        {corpus?.held_for_reference_not_clinical_guidelines?.length > 0 && (
          <p style={{ color: "#607371", fontSize: "0.76rem", margin: "-8px 0 16px" }}>
            {corpus.held_for_reference_not_clinical_guidelines.length} of these documents are held
            for reference only and are not clinical guidelines. A passage from one is labelled as
            such and is never a basis for a prescribing decision.
          </p>
        )}

        {/* EXAMPLE CHIPS */}
        <div className="example-chips" style={{ marginBottom: "16px" }}>
          {exampleQueries.map((q, idx) => (
            <button key={idx} className="example-chip" onClick={() => setQuestion(q)}>
              "{q}"
            </button>
          ))}
        </div>

        {/* SEARCH FORM */}
        <form onSubmit={handleSearch} style={{ display: "flex", gap: "10px", marginBottom: "20px" }}>
          <input
            type="text"
            placeholder="Ask a clinical question about guidelines, dosages, contraindications, or syndrome cover..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            className="dashboard-select"
            style={{ flex: 1 }}
          />
          <button className="dashboard-button primary" type="submit" disabled={loading} style={{ padding: "12px 24px" }}>
            <Search size={16} /> {loading ? "Searching..." : "Search Evidence"}
          </button>
        </form>

        {/* ERROR DISPLAY */}
        {error && (
          <div className="dashboard-empty" style={{ margin: "20px 0" }}>
            <ShieldAlert size={28} color="#a33d31" />
            <h2>This clinical tool is currently unavailable</h2>
            <p>{error}</p>
            <button className="dashboard-button primary" onClick={handleSearch}>
              Retry
            </button>
          </div>
        )}

        {/* SEARCH RESULTS DISPLAY */}
        {result && (
          <div style={{ marginTop: "20px" }}>
            {!result.answered ? (
              <div style={{ background: "#fbe9e5", border: "1px solid #e0b4ac", padding: "16px", borderRadius: "6px", color: "#a33d31" }}>
                <strong>Evidence Query Refused:</strong> {result.message || result.refusal_reason || "Insufficient evidence in corpus."}
              </div>
            ) : (
              <div style={{ display: "grid", gap: "14px" }}>
                {result.caveats?.map((c: string, idx: number) => (
                  <div
                    key={`caveat-${idx}`}
                    style={{ background: "#fdf3e3", border: "1px solid #e0c9a0", padding: "12px",
                             borderRadius: "6px", color: "#7a5520", fontSize: "0.8rem" }}
                  >
                    <ShieldAlert size={14} style={{ verticalAlign: "-2px", marginRight: "6px" }} />
                    {c}
                  </div>
                ))}

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "#173c3d" }}>
                    Retrieved {result.passage_count || result.passages?.length || 0} Verbatim Passage(s)
                  </span>
                  <span style={{ fontSize: "0.72rem", color: "#718281", background: "#eef6f2", padding: "4px 8px", borderRadius: "4px" }}>
                    Mode: {result.answer_mode || "EXTRACTIVE_NO_LLM"}
                  </span>
                </div>

                {result.passages?.map((p: any, idx: number) => (
                  <article
                    key={idx}
                    style={{
                      background: "#f0f6f1",
                      borderLeft: "4px solid #4e8a7a",
                      border: "1px solid #c8dcd2",
                      borderLeftWidth: "4px",
                      borderRadius: "6px",
                      padding: "16px",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem", marginBottom: "8px" }}>
                      <strong style={{ color: "#173c3d" }}>{p.document_title}</strong>
                      <span style={{ color: "#2d7064", fontWeight: 600 }}>Score: {p.retrieval_score ?? "N/A"}</span>
                    </div>

                    {/*
                      Standing, per passage.

                      clinical_standing only fires for precedence rank 4, so before
                      the corpus expansion it covered every passage that needed a
                      warning. It no longer does: an ICMR oncology consensus document
                      is a rank-2 clinical guideline with no standing whatsoever on
                      antimicrobial choice, and would otherwise appear here with the
                      same styling as the ICMR antimicrobial guidelines. The domain
                      caveat is the per-passage warning for that case.
                    */}
                    {(p.clinical_standing || p.domain_caveat) && (
                      <p style={{ fontSize: "0.74rem", color: "#8a4b1f", background: "#fdf3e3",
                                  border: "1px solid #e0c9a0", borderRadius: "4px",
                                  padding: "6px 8px", margin: "0 0 8px" }}>
                        {p.clinical_standing || p.domain_caveat}
                      </p>
                    )}

                    <p style={{ fontSize: "0.88rem", lineHeight: "1.55", margin: "8px 0", color: "#203236" }}>
                      “{p.verbatim_passage}”
                    </p>

                    <div style={{ display: "flex", gap: "14px", fontSize: "0.74rem", color: "#607371", marginTop: "8px" }}>
                      <span>Issuing Org: <strong>{p.issuing_org}</strong></span>
                      <span>Version: <strong>{p.guideline_version}</strong></span>
                      {p.section_page && <span>Location: <strong>{p.section_page}</strong></span>}
                    </div>
                  </article>
                ))}

                <p className="muted" style={{ fontSize: "0.74rem", marginTop: "8px" }}>
                  {result.disclaimer}
                </p>
              </div>
            )}
          </div>
        )}
      </section>
    </ClinicalToolsLayout>
  );
}
