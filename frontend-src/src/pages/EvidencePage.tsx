import { useState } from "react";
import { Search, BookOpenCheck, ShieldAlert } from "lucide-react";
import ClinicalToolsLayout from "@/components/ClinicalToolsLayout";
import "@/styles/patient-dashboard.css";

export default function EvidencePage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
          Search 2,276 verbatim guideline passages from ICMR STG 2022-23, WHO AWaRe 2023, and DailyMed drug labels. Answers are strictly extractive with score citations — no LLM hallucinations.
        </p>

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
