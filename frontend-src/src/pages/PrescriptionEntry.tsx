import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Plus, ShieldCheck, X } from "lucide-react";
import { Link, useLocation, useParams } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import { patientName } from "@/lib/patient";
import "@/styles/patient-dashboard.css";
import { useRuleCount, ruleEngineLabel } from "@/hooks/useRuleCount";

type PrescriptionItem = {
  medication_name: string;
  dose?: number;
  unit?: string;
  route?: string;
  frequency?: string;
  duration_days?: number;
  indication?: string;
};

export default function PrescriptionEntry() {
  // Read from the engine rather than restated from memory; see useRuleCount.
  const ruleCount = useRuleCount();
  const { patient_id, visit_id } = useParams<{ patient_id: string; visit_id: string }>();
  const [, setLocation] = useLocation();

  const [patient, setPatient] = useState<any>(null);
  const [visitDraft, setVisitDraft] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const [rawText, setRawText] = useState("");
  const [items, setItems] = useState<PrescriptionItem[]>([]);

  const [medName, setMedName] = useState("");
  const [medDose, setMedDose] = useState("");
  const [medUnit, setMedUnit] = useState("mg");
  const [medRoute, setMedRoute] = useState("PO");
  const [medFreq, setMedFreq] = useState("TID");
  const [medDur, setMedDur] = useState("5");

  const [error, setError] = useState("");
  const [extracting, setExtracting] = useState(false);

  useEffect(() => {
    async function init() {
      if (!patient_id) return;
      try {
        const res = await fetch(`/api/patients/${encodeURIComponent(patient_id)}/history`);
        if (res.ok) {
          const d = await res.json();
          setPatient(d.patient);
        }
        const draftStr = sessionStorage.getItem(`microbe:visit_draft:${patient_id}`);
        if (draftStr) {
          setVisitDraft(JSON.parse(draftStr));
        }
      } catch {
        // Keep silent
      } finally {
        setLoading(false);
      }
    }
    void init();
  }, [patient_id]);

  function addMedication() {
    if (!medName.trim()) return;
    setItems([
      ...items,
      {
        medication_name: medName.trim(),
        dose: medDose ? Number(medDose) : undefined,
        unit: medUnit,
        route: medRoute,
        frequency: medFreq,
        duration_days: medDur ? Number(medDur) : undefined,
        indication: visitDraft?.diagnosis,
      },
    ]);
    setMedName("");
    setMedDose("");
  }

  function removeItem(index: number) {
    setItems(items.filter((_, i) => i !== index));
  }

  async function handleExtractFreeText() {
    if (!rawText.trim()) return;
    setExtracting(true);
    try {
      const res = await fetch("/api/prescriptions/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_text: rawText }),
      });
      if (res.ok) {
        const extracted = await res.json();
        if (extracted.items && extracted.items.length > 0) {
          setItems(extracted.items);
        }
      }
    } catch {
      // Keep state
    } finally {
      setExtracting(false);
    }
  }

  function handleAnalyze(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (items.length === 0 && !rawText.trim()) {
      setError("Please add at least one medication order to perform clinical analysis.");
      return;
    }

    // Save prescription state in sessionStorage for the analysis step
    const updatedDraft = {
      ...visitDraft,
      raw_text: rawText,
      prescription_items: items,
    };
    sessionStorage.setItem(`microbe:visit_draft:${patient_id}`, JSON.stringify(updatedDraft));

    // Navigate to Page 6: Clinical Decision Support Analysis Page
    setLocation(`/patients/${patient_id}/visits/${visit_id}/analysis`);
  }

  if (loading) {
    return (
      <main className="dashboard-page">
        <div className="dashboard-empty">Loading prescription workspace...</div>
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
          <p className="dashboard-kicker">PATIENT WORKFLOW STEP 5</p>
          <h1>Create Prescription — {displayedName}</h1>
          <p className="dashboard-subtitle">
            {idPrefix}Current Diagnosis: <strong>{visitDraft?.diagnosis || "Not specified"}</strong> · Allergies: {patient?.allergies?.join(", ") || "None"}
          </p>
        </div>
        <Link href={`/patients/${patient_id}/visit/new`} className="dashboard-button secondary">
          <ArrowLeft size={15} /> Back to Visit Entry
        </Link>
      </div>

      <section className="info-section" style={{ maxWidth: "900px", margin: "0 auto" }}>
        <form onSubmit={handleAnalyze} style={{ display: "grid", gap: "18px" }}>
          <div>
            <p className="dashboard-kicker">PRESCRIPTION ENTRY & EXTRACTION</p>
            <h2>Add Prescribed Medications</h2>
          </div>

          {/* FREE TEXT EXTRACTION OPTION WITH CONFIRMATION GATE */}
          <div style={{ background: "#f0f6f1", border: "1px solid #c8dcd2", padding: "14px", borderRadius: "6px" }}>
            <label className="field-label" style={{ marginTop: 0 }}>Option A: Free-Text Order Extraction (With Confirmation Gate)</label>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                type="text"
                placeholder="e.g. Amoxicillin 500mg PO TID x 5 days for pneumonia"
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                className="dashboard-select"
              />
              <button type="button" className="dashboard-button secondary" onClick={handleExtractFreeText} disabled={extracting}>
                {extracting ? "Extracting..." : "Extract Order"}
              </button>
            </div>
            <p className="muted" style={{ margin: "6px 0 0", fontSize: "0.72rem" }}>
              Extraction parses per-field confidence. Clinician confirmation gate validates parsed items before 24-rule safety analysis.
            </p>
          </div>

          {/* STRUCTURED MEDICATION INPUT */}
          <div>
            <label className="field-label">Option B: Add Structured Medication Item</label>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <input placeholder="Drug name (e.g. Amoxicillin)" value={medName} onChange={(e) => setMedName(e.target.value)} style={{ flex: 2 }} className="dashboard-select" />
              <input placeholder="Dose" type="number" value={medDose} onChange={(e) => setMedDose(e.target.value)} style={{ width: "80px" }} className="dashboard-select" />
              <select value={medUnit} onChange={(e) => setMedUnit(e.target.value)} style={{ width: "70px" }} className="dashboard-select">
                <option value="mg">mg</option>
                <option value="g">g</option>
                <option value="mcg">mcg</option>
              </select>
              <select value={medRoute} onChange={(e) => setMedRoute(e.target.value)} style={{ width: "70px" }} className="dashboard-select">
                <option value="PO">PO</option>
                <option value="IV">IV</option>
                <option value="IM">IM</option>
              </select>
              <select value={medFreq} onChange={(e) => setMedFreq(e.target.value)} style={{ width: "80px" }} className="dashboard-select">
                <option value="QD">QD</option>
                <option value="BID">BID</option>
                <option value="TID">TID</option>
                <option value="QID">QID</option>
              </select>
              <input placeholder="Days" type="number" value={medDur} onChange={(e) => setMedDur(e.target.value)} style={{ width: "70px" }} className="dashboard-select" />
              <button type="button" className="dashboard-button secondary" onClick={addMedication}>
                <Plus size={15} /> Add Item
              </button>
            </div>
          </div>

          {/* CONFIRMED PRESCRIPTION ITEMS TABLE */}
          {items.length > 0 && (
            <div style={{ marginTop: "10px" }}>
              <strong style={{ color: "#173c3d", fontSize: "0.9rem" }}>Confirmed Prescription Items for Analysis ({items.length}):</strong>
              <table className="patient-table" style={{ marginTop: "8px" }}>
                <thead>
                  <tr>
                    <th>Medication Name</th>
                    <th>Dose / Route</th>
                    <th>Frequency</th>
                    <th>Duration</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, idx) => (
                    <tr key={idx}>
                      <td><strong>{item.medication_name}</strong></td>
                      <td>{item.dose} {item.unit} {item.route}</td>
                      <td>{item.frequency}</td>
                      <td>{item.duration_days} days</td>
                      <td>
                        <X size={14} style={{ cursor: "pointer", color: "#a33d31" }} onClick={() => removeItem(idx)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {error && <p className="form-error">{error}</p>}

          <div style={{ marginTop: "14px", display: "flex", gap: "10px" }}>
            <button className="dashboard-button warning" type="submit" style={{ padding: "12px 20px" }}>
              <ShieldCheck size={16} /> Analyze Prescription ({ruleEngineLabel(ruleCount)}) <ArrowRight size={16} />
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
