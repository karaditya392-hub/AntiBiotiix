import { useEffect, useState } from "react";
import { ArrowRight, History, Plus, X } from "lucide-react";
import { useLocation, useParams } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import { patientName } from "@/lib/patient";
import "@/styles/patient-dashboard.css";

type Symptom = {
  name: string;
  severity?: string;
  duration?: string;
  onset?: string;
  notes?: string;
};

export default function NewVisitEntry() {
  const { patient_id } = useParams<{ patient_id: string }>();
  const [, setLocation] = useLocation();

  const [patient, setPatient] = useState<any>(null);
  const [previousVisit, setPreviousVisit] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const [diagnosis, setDiagnosis] = useState("");
  const [clinicalNotes, setClinicalNotes] = useState("");
  const [symptoms, setSymptoms] = useState<Symptom[]>([]);

  const [symName, setSymName] = useState("");
  const [symSeverity, setSymSeverity] = useState("Moderate");
  const [symDuration, setSymDuration] = useState("3 days");
  const [error, setError] = useState("");

  async function loadData() {
    if (!patient_id) return;
    try {
      const res = await fetch(`/api/patients/${encodeURIComponent(patient_id)}/history`);
      if (res.ok) {
        const data = await res.json();
        setPatient(data.patient);
        if (data.visits && data.visits.length > 0) {
          setPreviousVisit(data.visits[0]);
        }
      }
    } catch {
      // Keep silent
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, [patient_id]);

  function addSymptom() {
    if (!symName.trim()) return;
    setSymptoms([
      ...symptoms,
      { name: symName.trim(), severity: symSeverity, duration: symDuration },
    ]);
    setSymName("");
  }

  function removeSymptom(index: number) {
    setSymptoms(symptoms.filter((_, i) => i !== index));
  }

  function handleContinueToPrescription(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!diagnosis.trim()) {
      setError("Diagnosis is required to proceed to prescription creation.");
      return;
    }

    // Store current visit state in sessionStorage for step-by-step workflow
    const tempVisitId = `VIS-${Math.random().toString(36).substr(2, 6).toUpperCase()}`;
    const visitData = {
      visit_id: tempVisitId,
      patient_id,
      diagnosis: diagnosis.trim(),
      clinical_notes: clinicalNotes.trim(),
      symptoms,
    };
    sessionStorage.setItem(`microbe:visit_draft:${patient_id}`, JSON.stringify(visitData));

    // Navigate to Page 5: Prescription Entry
    setLocation(`/patients/${patient_id}/visits/${tempVisitId}/prescription`);
  }

  if (loading) {
    return (
      <main className="dashboard-page">
        <div className="dashboard-empty">Loading visit workspace...</div>
      </main>
    );
  }

  // Lead with the name; the record id stays in the subtitle, but drop it there
  // when no name was captured and the heading is already showing the id.
  const displayedName = patientName(patient?.display_name, patient_id);
  const idPrefix = displayedName === patient_id ? "" : `${patient_id} · `;

  return (
    <main className="dashboard-page">
      <UnifiedHeader />

      <div className="dashboard-header" style={{ marginBottom: "16px" }}>
        <div>
          <p className="dashboard-kicker">PATIENT WORKFLOW STEP 4</p>
          <h1>New Visit — {displayedName}</h1>
          <p className="dashboard-subtitle">
            {idPrefix}{patient?.age ?? "Unknown"} years · {patient?.sex || "Sex unrecorded"} · Documented Allergies: {patient?.allergies?.join(", ") || "None"}
          </p>
        </div>
        <div style={{ display: "flex", gap: "10px" }}>
          <button className="dashboard-button secondary" onClick={() => setLocation(`/patients/${patient_id}`)}>
            <History size={15} /> View Patient History
          </button>
        </div>
      </div>

      {/* PREVIOUS VISIT SUMMARY (ONLY FOR RETURNING PATIENTS) */}
      {previousVisit ? (
        <section className="previous-visit-panel" style={{ maxWidth: "900px", margin: "0 auto 20px" }}>
          <h4>
            PREVIOUS VISIT SUMMARY (Last visit:{" "}
            {previousVisit.formatted_date ||
              new Date(previousVisit.visit_date).toLocaleString("en-US", {
                weekday: "long",
                year: "numeric",
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit",
                hour12: true,
              })}
            )
          </h4>
          <p style={{ margin: "4px 0", fontSize: "0.85rem" }}>
            <b>Previous Diagnosis:</b> {previousVisit.diagnosis || "Not recorded"}
          </p>
          <p style={{ margin: "4px 0", fontSize: "0.85rem" }}>
            <b>Previous Prescription:</b>{" "}
            {previousVisit.medications.map((m: any) => `${m.name} ${m.dose ? `${m.dose}${m.unit || ""}` : ""} ${m.frequency || ""}`).join(" · ") || "None"}
          </p>
          <p style={{ margin: "4px 0", fontSize: "0.85rem" }}>
            <b>Allergies & Provenance:</b> {patient?.allergies?.join(", ") || "None documented"}
          </p>
        </section>
      ) : (
        <section className="previous-visit-panel" style={{ maxWidth: "900px", margin: "0 auto 20px" }}>
          <h4>INITIAL VISIT RECORD</h4>
          <p style={{ margin: 0, fontSize: "0.85rem" }}>This will be the patient's first recorded historical visit.</p>
        </section>
      )}

      {/* CURRENT VISIT FORM */}
      <section className="info-section" style={{ maxWidth: "900px", margin: "0 auto" }}>
        <form onSubmit={handleContinueToPrescription} style={{ display: "grid", gap: "16px" }}>
          <div>
            <p className="dashboard-kicker">CURRENT VISIT FINDINGS</p>
            <h2>Record Symptoms & Diagnosis</h2>
          </div>

          <div>
            <label className="field-label">Current Diagnosis *</label>
            <input
              type="text"
              placeholder="e.g. Community-acquired pneumonia or Acute cystitis"
              value={diagnosis}
              onChange={(e) => setDiagnosis(e.target.value)}
              required
              className="dashboard-select"
            />
          </div>

          <div>
            <label className="field-label">Record Structured Symptoms</label>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                type="text"
                placeholder="Symptom (e.g. Fever, Productive cough)"
                value={symName}
                onChange={(e) => setSymName(e.target.value)}
                style={{ flex: 2 }}
                className="dashboard-select"
              />
              <select value={symSeverity} onChange={(e) => setSymSeverity(e.target.value)} style={{ flex: 1 }} className="dashboard-select">
                <option value="Mild">Mild</option>
                <option value="Moderate">Moderate</option>
                <option value="Severe">Severe</option>
              </select>
              <input
                type="text"
                placeholder="Duration (e.g. 3 days)"
                value={symDuration}
                onChange={(e) => setSymDuration(e.target.value)}
                style={{ flex: 1 }}
                className="dashboard-select"
              />
              <button type="button" className="dashboard-button secondary" onClick={addSymptom}>
                <Plus size={15} /> Add
              </button>
            </div>

            {symptoms.length > 0 && (
              <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "10px" }}>
                {symptoms.map((s, idx) => (
                  <span className="symptom-tag" key={idx}>
                    {s.name} ({s.severity}, {s.duration})
                    <X size={12} style={{ cursor: "pointer" }} onClick={() => removeSymptom(idx)} />
                  </span>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="field-label">Clinical Examination Notes</label>
            <textarea
              rows={3}
              placeholder="Record physical examination notes, vitals, or clinical rationale..."
              value={clinicalNotes}
              onChange={(e) => setClinicalNotes(e.target.value)}
              className="dashboard-select"
            />
          </div>

          {error && <p className="form-error">{error}</p>}

          <div style={{ marginTop: "12px", display: "flex", gap: "10px" }}>
            <button className="dashboard-button primary" type="submit" style={{ padding: "12px 20px" }}>
              Continue to Prescription <ArrowRight size={16} />
            </button>
            <button className="dashboard-button secondary" type="button" onClick={() => setLocation(`/patients/${patient_id}`)}>
              Cancel
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
