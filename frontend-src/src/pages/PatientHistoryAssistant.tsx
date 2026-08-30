import { useEffect, useState } from "react";
import { ArrowLeft, BookOpenCheck } from "lucide-react";
import { Link, useLocation, useParams } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import { patientName } from "@/lib/patient";
import "@/styles/patient-dashboard.css";

export default function PatientHistoryAssistant() {
  const { patient_id } = useParams<{ patient_id: string }>();
  const [, setLocation] = useLocation();

  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [patient, setPatient] = useState<any>(null);

  // The page only ever needed the id to query with, but a clinician should see
  // whose records they are asking about.
  useEffect(() => {
    if (!patient_id) return;
    (async () => {
      try {
        const res = await fetch(`/api/patients/${encodeURIComponent(patient_id)}`);
        if (res.ok) setPatient(await res.json());
      } catch {
        // Non-fatal: the heading falls back to the record id.
      }
    })();
  }, [patient_id]);

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!patient_id || !question.trim()) return;
    setLoading(true);
    setAnswer(null);

    try {
      const login = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "CLINICIAN-DEMO", role: "ATTENDING_PHYSICIAN" }),
      });
      const auth = await login.json();

      const res = await fetch(`/api/patients/${encodeURIComponent(patient_id)}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${auth.access_token}`,
        },
        body: JSON.stringify({ question: question.trim() }),
      });
      if (res.ok) {
        setAnswer(await res.json());
      }
    } catch {
      // Keep silent
    } finally {
      setLoading(false);
    }
  }

  const displayedName = patientName(patient?.display_name, patient_id);
  const idSuffix = displayedName === patient_id ? "" : ` (${patient_id})`;

  return (
    <main className="dashboard-page">
      <UnifiedHeader />

      <div className="dashboard-header" style={{ marginBottom: "16px" }}>
        <div>
          <p className="dashboard-kicker">PATIENT RAG RETRIEVAL LAYER</p>
          <h1>Ask About {displayedName}'s History</h1>
          <p className="dashboard-subtitle">
            Answers are grounded EXCLUSIVELY in <strong>{displayedName}</strong>'s stored records{idSuffix} with strict patient isolation.
          </p>
        </div>
        <Link href={`/patients/${patient_id}`} className="dashboard-button secondary">
          <ArrowLeft size={15} /> Back to Profile
        </Link>
      </div>

      <section className="ask-assistant-box" style={{ maxWidth: "900px", margin: "0 auto" }}>
        <div className="section-title-row">
          <div>
            <p className="dashboard-kicker">EVIDENCE-GROUNDED HISTORY RETRIEVAL</p>
            <h2>Natural Language Query Assistant</h2>
          </div>
          <BookOpenCheck size={24} color="#2d7064" />
        </div>

        <div className="example-chips" style={{ margin: "14px 0" }}>
          <button className="example-chip" onClick={() => setQuestion("What was the diagnosis during the last visit?")}>
            "What was the diagnosis during the last visit?"
          </button>
          <button className="example-chip" onClick={() => setQuestion("What medications has this patient received?")}>
            "What medications has this patient received?"
          </button>
          <button className="example-chip" onClick={() => setQuestion("What symptoms did the patient have previously?")}>
            "What symptoms did the patient have previously?"
          </button>
          <button className="example-chip" onClick={() => setQuestion("When was the patient's last visit?")}>
            "When was the patient's last visit?"
          </button>
          <button className="example-chip" onClick={() => setQuestion("What was prescribed two visits ago?")}>
            "What was prescribed two visits ago?"
          </button>
        </div>

        <form className="ask-input-row" onSubmit={handleAsk}>
          <input
            type="text"
            placeholder="Ask a question about this patient's history..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            className="dashboard-select"
          />
          <button className="dashboard-button primary" type="submit" disabled={loading}>
            {loading ? "Searching..." : "Ask History Assistant"}
          </button>
        </form>

        {answer && (
          <div className="ask-answer-card">
            <pre>{answer.answer}</pre>
            {answer.source_visit_id && (
              <div
                className="source-citation-link"
                onClick={() => setLocation(`/patients/${patient_id}`)}
              >
                Source: Visit {answer.source_visit_id} (Click to open visit in patient timeline)
              </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
