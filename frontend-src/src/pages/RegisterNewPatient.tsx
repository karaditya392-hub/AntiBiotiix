import { useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, UserRound, FileText, Pill } from "lucide-react";
import { Link, useLocation } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import "@/styles/patient-dashboard.css";

export default function RegisterNewPatient() {
  const [, setLocation] = useLocation();
  const [activeTab, setActiveTab] = useState<"demographics" | "history" | "notes">("demographics");

  const [form, setForm] = useState({
    name: "",
    age: "",
    sex: "MALE",
    weight: "",
    egfr: "",
    childPugh: "",
    pregnancy: "CONFIRMED_NOT_PREGNANT",
    lactation: "CONFIRMED_NOT_LACTATING",
    allergies: "",
    medications: "",
    medicalHistory: "",
    notes: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!form.name.trim()) {
      setError("Patient full name is required to create the record.");
      setActiveTab("demographics");
      return;
    }
    if (!form.age) {
      setError("Patient age is required to create the record.");
      setActiveTab("demographics");
      return;
    }
    setSubmitting(true);

    try {
      const login = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "CLINICIAN-DEMO", role: "ATTENDING_PHYSICIAN" }),
      });
      const auth = await login.json();

      const payload = {
        display_name: form.name.trim(),
        age: Number(form.age),
        age_category: Number(form.age) >= 18 ? "ADULT" : "CHILD",
        sex: form.sex,
        weight_kg: form.weight ? Number(form.weight) : undefined,
        egfr_ml_min: form.egfr ? Number(form.egfr) : undefined,
        renal_status_known: Boolean(form.egfr),
        hepatic_status_known: Boolean(form.childPugh),
        child_pugh_class: form.childPugh || undefined,
        pregnancy_status: form.pregnancy,
        lactation_status: form.lactation,
        allergy_status_known: Boolean(form.allergies),
        active_medications: form.medications.split("\n").map((v) => v.trim()).filter(Boolean),
        medical_history: form.medicalHistory.split(",").map((v) => v.trim()).filter(Boolean),
        clinical_notes: form.notes || undefined,
      };

      const res = await fetch("/api/patients", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${auth.access_token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        setError("Failed to register patient. Check entered values.");
        setSubmitting(false);
        return;
      }

      const created = await res.json();

      if (form.allergies.trim()) {
        for (const substance of form.allergies.split(",").map((v) => v.trim()).filter(Boolean)) {
          await fetch(`/api/patients/${created.patient_id}/allergies`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${auth.access_token}`,
            },
            body: JSON.stringify({ substance }),
          });
        }
      }

      // Automatically navigate to Page 4: New Visit Entry
      setLocation(`/patients/${created.patient_id}/visit/new`);
    } catch {
      setError("An error occurred during registration.");
      setSubmitting(false);
    }
  }

  return (
    <main className="dashboard-page">
      <UnifiedHeader />

      <div className="dashboard-header" style={{ marginBottom: "16px" }}>
        <div>
          <p className="dashboard-kicker">PATIENT WORKFLOW STEP 2B</p>
          <h1>Register New Patient</h1>
          <p className="dashboard-subtitle">Create a patient record and begin their first visit.</p>
        </div>
        <Link href="/patient-type" className="dashboard-button secondary">
          <ArrowLeft size={15} /> Back to Selection
        </Link>
      </div>

      <section className="register-form-card" style={{ maxWidth: "920px", margin: "0 auto" }}>
        {/* LARGE TABS BAR FOR NEW PATIENT REGISTRATION */}
        <div className="register-tabs-container">
          <button
            type="button"
            className={`register-tab-btn ${activeTab === "demographics" ? "active" : ""}`}
            onClick={() => setActiveTab("demographics")}
          >
            <UserRound size={18} /> 1. Demographics & Organ Function
          </button>
          <button
            type="button"
            className={`register-tab-btn ${activeTab === "history" ? "active" : ""}`}
            onClick={() => setActiveTab("history")}
          >
            <Pill size={18} /> 2. Allergies & Medical History
          </button>
          <button
            type="button"
            className={`register-tab-btn ${activeTab === "notes" ? "active" : ""}`}
            onClick={() => setActiveTab("notes")}
          >
            <FileText size={18} /> 3. Clinical Notes & Initial Visit
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Rendered outside the tab panels: a validation failure switches tabs,
              and the reason has to travel with the clinician. */}
          {error && <p className="form-error">{error}</p>}

          {/* TAB 1: DEMOGRAPHICS & ORGAN FUNCTION */}
          {activeTab === "demographics" && (
            <div style={{ display: "grid", gap: "20px" }}>
              <div>
                <label className="field-label">Patient Full Name (e.g. Rajesh Sharma, Sunita Devi) *</label>
                <input
                  type="text"
                  placeholder="Enter full Indian patient name..."
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  style={{ width: "100%" }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "16px" }}>
                <div>
                  <label className="field-label">Age (years) *</label>
                  <input
                    type="number"
                    min="0"
                    max="125"
                    placeholder="e.g. 45"
                    value={form.age}
                    onChange={(e) => setForm({ ...form, age: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="field-label">Biological Sex *</label>
                  <select value={form.sex} onChange={(e) => setForm({ ...form, sex: e.target.value })}>
                    <option value="MALE">Male</option>
                    <option value="FEMALE">Female</option>
                    <option value="UNKNOWN">Unknown</option>
                  </select>
                </div>
                <div>
                  <label className="field-label">Weight (kg)</label>
                  <input
                    type="number"
                    step="0.1"
                    placeholder="e.g. 70"
                    value={form.weight}
                    onChange={(e) => setForm({ ...form, weight: e.target.value })}
                  />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                <div>
                  <label className="field-label">Renal Function (eGFR mL/min)</label>
                  <input
                    type="number"
                    placeholder="e.g. 90 (CKD-EPI formula)"
                    value={form.egfr}
                    onChange={(e) => setForm({ ...form, egfr: e.target.value })}
                  />
                </div>
                <div>
                  <label className="field-label">Hepatic Status</label>
                  <select value={form.childPugh} onChange={(e) => setForm({ ...form, childPugh: e.target.value })}>
                    <option value="">Normal / Not impaired</option>
                    <option value="Child-Pugh A">Child-Pugh A</option>
                    <option value="Child-Pugh B">Child-Pugh B</option>
                    <option value="Child-Pugh C">Child-Pugh C</option>
                  </select>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                <div>
                  <label className="field-label">Pregnancy Status</label>
                  <select value={form.pregnancy} onChange={(e) => setForm({ ...form, pregnancy: e.target.value })}>
                    <option value="CONFIRMED_NOT_PREGNANT">Confirmed Not Pregnant</option>
                    <option value="PREGNANT_TRIMESTER_1">Pregnant (1st Trimester)</option>
                    <option value="PREGNANT_TRIMESTER_2">Pregnant (2nd Trimester)</option>
                    <option value="PREGNANT_TRIMESTER_3">Pregnant (3rd Trimester)</option>
                    <option value="UNKNOWN">Unknown</option>
                  </select>
                </div>
                <div>
                  <label className="field-label">Lactation Status</label>
                  <select value={form.lactation} onChange={(e) => setForm({ ...form, lactation: e.target.value })}>
                    <option value="CONFIRMED_NOT_LACTATING">Confirmed Not Lactating</option>
                    <option value="LACTATING">Lactating</option>
                    <option value="UNKNOWN">Unknown</option>
                  </select>
                </div>
              </div>

              <div style={{ marginTop: "16px", display: "flex", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="dashboard-button primary"
                  style={{ padding: "12px 24px", fontSize: "0.9rem" }}
                  onClick={() => setActiveTab("history")}
                >
                  Next Step: Allergies & History <ArrowRight size={16} />
                </button>
              </div>
            </div>
          )}

          {/* TAB 2: ALLERGIES & MEDICAL HISTORY */}
          {activeTab === "history" && (
            <div style={{ display: "grid", gap: "20px" }}>
              <div>
                <label className="field-label">Documented Medication Allergies</label>
                <input
                  placeholder="Comma-separated (e.g. Penicillin, Sulfonamides, Amoxicillin)"
                  value={form.allergies}
                  onChange={(e) => setForm({ ...form, allergies: e.target.value })}
                />
                <p className="muted" style={{ marginTop: "4px", fontSize: "0.76rem" }}>
                  Allergies trigger the 24-rule safety engine checks. Clinician-entered allergies carry verified provenance.
                </p>
              </div>

              <div>
                <label className="field-label">Relevant Medical History & Chronic Conditions</label>
                <input
                  placeholder="Comma-separated (e.g. Hypertension, Asthma, Type 2 Diabetes, CKD Stage 3)"
                  value={form.medicalHistory}
                  onChange={(e) => setForm({ ...form, medicalHistory: e.target.value })}
                />
              </div>

              <div>
                <label className="field-label">Current Home / Inpatient Medications</label>
                <textarea
                  rows={3}
                  placeholder="Enter active medications (e.g. Pantoprazole 40mg PO QD, Aspirin 81mg PO QD)"
                  value={form.medications}
                  onChange={(e) => setForm({ ...form, medications: e.target.value })}
                />
              </div>

              <div style={{ marginTop: "16px", display: "flex", justifyContent: "space-between" }}>
                <button
                  type="button"
                  className="dashboard-button secondary"
                  style={{ padding: "12px 20px" }}
                  onClick={() => setActiveTab("demographics")}
                >
                  <ArrowLeft size={16} /> Back to Demographics
                </button>
                <button
                  type="button"
                  className="dashboard-button primary"
                  style={{ padding: "12px 24px", fontSize: "0.9rem" }}
                  onClick={() => setActiveTab("notes")}
                >
                  Next Step: Clinical Notes <ArrowRight size={16} />
                </button>
              </div>
            </div>
          )}

          {/* TAB 3: CLINICAL NOTES & INITIAL VISIT */}
          {activeTab === "notes" && (
            <div style={{ display: "grid", gap: "20px" }}>
              <div>
                <label className="field-label">Initial Presentation & Clinical Notes</label>
                <textarea
                  rows={4}
                  placeholder="Record initial clinical presentation, chief complaints, physical findings, and vitals..."
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                />
              </div>


              <div style={{ marginTop: "16px", display: "flex", justifyContent: "space-between" }}>
                <button
                  type="button"
                  className="dashboard-button secondary"
                  style={{ padding: "12px 20px" }}
                  onClick={() => setActiveTab("history")}
                >
                  <ArrowLeft size={16} /> Back to History
                </button>
                <button
                  type="submit"
                  className="dashboard-button primary"
                  style={{ padding: "14px 28px", fontSize: "0.95rem" }}
                  disabled={submitting}
                >
                  {submitting ? "Registering..." : "Create Patient & Begin First Visit"} <CheckCircle2 size={18} />
                </button>
              </div>
            </div>
          )}
        </form>
      </section>
    </main>
  );
}
