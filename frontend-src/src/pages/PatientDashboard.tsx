import { useEffect, useRef, useState } from "react";
import {
  ArrowRight, BookOpenCheck, FileWarning, History, Plus,
  ShieldCheck, UserRound, X, Pill, CheckCircle2, LayoutDashboard, Wrench
} from "lucide-react";
import { Link } from "wouter";
import "@/styles/patient-dashboard.css";
import { useRuleCount, ruleEngineLabel } from "@/hooks/useRuleCount";
import { patientName } from "@/lib/patient";

type Patient = {
  id?: number;
  patient_id: string;
  display_name?: string;
  age?: number;
  age_category?: string;
  sex?: string;
  weight_kg?: number;
  allergies?: string[];
  allergy_records?: Array<Record<string, string>>;
  allergy_status_known?: boolean;
  medical_history?: string[];
  egfr_ml_min?: number;
  renal_status_known?: boolean;
  child_pugh_class?: string;
  hepatic_status_known?: boolean;
  pregnancy_status?: string;
  lactation_status?: string;
  active_medications?: string[];
  clinical_notes?: string;
  last_visit?: string;
  last_diagnosis?: string;
};

type Symptom = {
  name: string;
  severity?: string;
  duration?: string;
  onset?: string;
  notes?: string;
};

type PrescriptionItem = {
  medication_name: string;
  dose?: number;
  unit?: string;
  route?: string;
  frequency?: string;
  duration_days?: number;
  indication?: string;
};

type Visit = {
  visit_id: string;
  prescription_id?: string;
  visit_date: string;
  diagnosis?: string;
  clinical_notes?: string;
  clinician_id?: string;
  clinician_role?: string;
  status?: string;
  symptoms?: Symptom[];
  medications: Array<Record<string, any>>;
  findings: Array<Record<string, string>>;
  overrides: Array<Record<string, string>>;
};

type History = {
  patient: Patient;
  visits: Visit[];
  audit: Array<Record<string, string>>;
};

type ScenarioPreset = {
  key: string;
  label: string;
  patient_id: string;
  diagnosis: string;
  text: string;
  source: string;
};

type DashboardStats = {
  total_patients: number;
  total_visits: number;
  total_prescriptions: number;
  total_active_warnings: number;
  critical_warnings_count: number;
  recent_patients: Patient[];
};

const emptyForm = {
  name: "",
  age: "",
  sex: "UNKNOWN",
  weight: "",
  egfr: "",
  childPugh: "",
  pregnancy: "UNKNOWN",
  lactation: "UNKNOWN",
  allergies: "",
  medications: "",
  medicalHistory: "",
  notes: "",
  diagnosis: "",
};

function display(value: unknown): string {
  return value === null || value === undefined || value === "" ? "Not recorded" : String(value);
}

function formatDate(value?: string): string {
  if (!value) return "Not recorded";
  try {
    const d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleString("en-US", {
      weekday: "long",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return String(value);
  }
}

export default function PatientDashboard() {
  // Read from the engine rather than restated from memory; see useRuleCount.
  const ruleCount = useRuleCount();
  const [activeTab, setActiveTab] = useState<"dashboard" | "patient" | "new_visit" | "medications" | "audit">("dashboard");
  const [patients, setPatients] = useState<Patient[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [history, setHistory] = useState<History | null>(null);
  const [mode, setMode] = useState<"returning" | "new">("returning");
  const [regForm, setRegForm] = useState(emptyForm);
  const [formError, setFormError] = useState("");
  const [_loading, setLoading] = useState(true);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [presets, setPresets] = useState<ScenarioPreset[]>([]);
  const [highlightedVisitId, setHighlightedVisitId] = useState<string | null>(null);

  // New Visit Form state
  const [newVisitDiagnosis, setNewVisitDiagnosis] = useState("");
  const [newVisitNotes, setNewVisitNotes] = useState("");
  const [symptomsList, setSymptomsList] = useState<Symptom[]>([]);
  const [symName, setSymName] = useState("");
  const [symSeverity, setSymSeverity] = useState("Moderate");
  const [symDuration, setSymDuration] = useState("3 days");

  const [prescriptionRawText, setPrescriptionRawText] = useState("");
  const [prescriptionItems, setPrescriptionItems] = useState<PrescriptionItem[]>([]);
  const [medName, setMedName] = useState("");
  const [medDose, setMedDose] = useState("");
  const [medUnit, setMedUnit] = useState("mg");
  const [medRoute, setMedRoute] = useState("PO");
  const [medFreq, setMedFreq] = useState("TID");
  const [medDur, setMedDur] = useState("5");

  const [safetyWarnings, setSafetyWarnings] = useState<any[]>([]);
  const [analysisStatus, setAnalysisStatus] = useState<string>("");
  const [visitSavedMsg, setVisitSavedMsg] = useState<string>("");

  // Ask About Patient state
  const [patientQuestion, setPatientQuestion] = useState("");
  const [patientAnswer, setPatientAnswer] = useState<any>(null);
  const [askLoading, setAskLoading] = useState(false);

  const historyRequest = useRef(0);

  async function loadDashboardStats() {
    try {
      const res = await fetch("/api/dashboard/stats");
      if (res.ok) setStats(await res.json());
    } catch {
      // Keep silent
    }
  }

  async function loadPresets() {
    try {
      const res = await fetch("/api/scenario-presets");
      if (res.ok) setPresets(await res.json());
    } catch {
      // Keep silent
    }
  }

  async function loadRoster(preferred?: string) {
    try {
      const url = searchQuery.trim() ? `/api/patients?q=${encodeURIComponent(searchQuery.trim())}` : "/api/patients";
      const response = await fetch(url);
      if (!response.ok) throw new Error("Patient service unavailable");
      const rows: Patient[] = await response.json();
      setPatients(rows);

      const saved = sessionStorage.getItem("antibiotix:selectedPatient");
      let id = "";
      if (preferred && rows.some((r) => r.patient_id === preferred)) {
        id = preferred;
      } else if (selectedId && rows.some((r) => r.patient_id === selectedId)) {
        id = selectedId;
      } else if (saved && rows.some((r) => r.patient_id === saved)) {
        id = saved;
      } else if (rows.length > 0) {
        id = rows[0].patient_id;
      }
      if (id && !selectedId) {
        setSelectedId(id);
        void loadHistory(id);
      }
    } catch {
      // Keep state clean
    } finally {
      setLoading(false);
    }
  }

  async function loadHistory(id: string) {
    const request = ++historyRequest.current;
    setHistory(null);
    setPatientAnswer(null);
    try {
      const response = await fetch(`/api/patients/${encodeURIComponent(id)}/history`);
      const data = response.ok ? await response.json() : null;
      if (request === historyRequest.current) setHistory(data);
    } finally {
      // Done
    }
  }

  useEffect(() => {
    void loadRoster();
    void loadPresets();
    void loadDashboardStats();
  }, []);

  useEffect(() => {
    void loadRoster();
  }, [searchQuery]);

  useEffect(() => {
    if (selectedId) {
      sessionStorage.setItem("antibiotix:selectedPatient", selectedId);
      void loadHistory(selectedId);
    }
  }, [selectedId]);

  function selectPatient(id: string, tab: "patient" | "new_visit" | "medications" = "patient") {
    setSelectedId(id);
    setActiveTab(tab);
    void loadHistory(id);
  }

  async function registerPatient(event: React.FormEvent) {
    event.preventDefault();
    setFormError("");
    if (!regForm.name.trim() || !regForm.age || regForm.sex === "UNKNOWN" || !regForm.diagnosis.trim()) {
      setFormError("Full name, age, sex, and a diagnosis or reason for visit are required to create the initial record.");
      return;
    }
    const login = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "CLINICIAN-DEMO", role: "ATTENDING_PHYSICIAN" }),
    });
    const auth = await login.json();
    const payload = {
      display_name: regForm.name.trim(),
      age: Number(regForm.age),
      age_category: Number(regForm.age) >= 18 ? "ADULT" : "CHILD",
      sex: regForm.sex,
      weight_kg: regForm.weight ? Number(regForm.weight) : undefined,
      egfr_ml_min: regForm.egfr ? Number(regForm.egfr) : undefined,
      renal_status_known: Boolean(regForm.egfr),
      hepatic_status_known: Boolean(regForm.childPugh),
      child_pugh_class: regForm.childPugh || undefined,
      pregnancy_status: regForm.pregnancy,
      lactation_status: regForm.lactation,
      allergy_status_known: Boolean(regForm.allergies),
      active_medications: regForm.medications.split("\n").map((v) => v.trim()).filter(Boolean),
      medical_history: regForm.medicalHistory.split(",").map((v) => v.trim()).filter(Boolean),
      clinical_notes: regForm.notes || undefined,
    };
    const response = await fetch("/api/patients", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${auth.access_token}`,
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      setFormError("The patient could not be registered. Check entered values.");
      return;
    }
    const created = await response.json();
    if (regForm.allergies.trim()) {
      for (const substance of regForm.allergies.split(",").map((v) => v.trim()).filter(Boolean)) {
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

    // Save initial visit
    await fetch(`/api/patients/${created.patient_id}/visits`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${auth.access_token}`,
      },
      body: JSON.stringify({
        patient_id: created.patient_id,
        diagnosis: regForm.diagnosis.trim(),
        clinical_notes: regForm.notes.trim() || undefined,
        symptoms: [],
        prescription_items: [],
      }),
    });

    setRegForm(emptyForm);
    setMode("returning");
    await loadRoster(created.patient_id);
    await loadPresets();
    await loadDashboardStats();
    selectPatient(created.patient_id, "patient");
  }

  function addSymptom() {
    if (!symName.trim()) return;
    setSymptomsList([
      ...symptomsList,
      { name: symName.trim(), severity: symSeverity, duration: symDuration },
    ]);
    setSymName("");
  }

  function removeSymptom(index: number) {
    setSymptomsList(symptomsList.filter((_, i) => i !== index));
  }

  function addMedication() {
    if (!medName.trim()) return;
    setPrescriptionItems([
      ...prescriptionItems,
      {
        medication_name: medName.trim(),
        dose: medDose ? Number(medDose) : undefined,
        unit: medUnit,
        route: medRoute,
        frequency: medFreq,
        duration_days: medDur ? Number(medDur) : undefined,
      },
    ]);
    setMedName("");
    setMedDose("");
  }

  function removeMedication(index: number) {
    setPrescriptionItems(prescriptionItems.filter((_, i) => i !== index));
  }

  async function runSafetyAnalysis() {
    if (!selectedId) return;
    setAnalysisStatus("Evaluating 24 clinical safety rules...");
    try {
      await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "CLINICIAN-DEMO", role: "ATTENDING_PHYSICIAN" }),
      });

      // Submit temp prescription order to run rule engine
      const prescRes = await fetch("/api/prescriptions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: selectedId,
          diagnosis: newVisitDiagnosis,
          raw_text: prescriptionRawText,
          items: prescriptionItems,
        }),
      });
      if (!prescRes.ok) throw new Error("Could not submit prescription");
      const prescData = await prescRes.json();

      const analyzeRes = await fetch(`/api/prescriptions/${prescData.prescription_id}/analyze`, {
        method: "POST",
      });
      if (analyzeRes.ok) {
        const analyzeData = await analyzeRes.json();
        setSafetyWarnings(analyzeData.warnings || []);
        setAnalysisStatus(`Analysis complete: ${analyzeData.total_warnings} safety finding(s) surfaced.`);
      }
    } catch {
      setAnalysisStatus("Analysis failed to complete.");
    }
  }

  async function saveVisit(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedId || !newVisitDiagnosis.trim()) {
      setFormError("Diagnosis is required to save the visit.");
      return;
    }
    setVisitSavedMsg("");
    setFormError("");

    const login = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "CLINICIAN-DEMO", role: "ATTENDING_PHYSICIAN" }),
    });
    const auth = await login.json();

    const visitPayload = {
      patient_id: selectedId,
      doctor_id: "DOC-DEMO-01",
      diagnosis: newVisitDiagnosis.trim(),
      symptoms: symptomsList,
      symptoms_text: symptomsList.map((s) => `${s.name} (${s.severity}, ${s.duration})`).join(", "),
      clinical_notes: newVisitNotes.trim() || undefined,
      raw_prescription_text: prescriptionRawText.trim() || undefined,
      prescription_items: prescriptionItems,
    };

    const res = await fetch(`/api/patients/${selectedId}/visits`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${auth.access_token}`,
      },
      body: JSON.stringify(visitPayload),
    });

    if (res.ok) {
      setVisitSavedMsg("Visit saved successfully and indexed for RAG retrieval.");
      setNewVisitDiagnosis("");
      setNewVisitNotes("");
      setSymptomsList([]);
      setPrescriptionRawText("");
      setPrescriptionItems([]);
      setSafetyWarnings([]);
      setAnalysisStatus("");
      await loadHistory(selectedId);
      await loadDashboardStats();
      setActiveTab("patient");
    } else {
      setFormError("Failed to save visit. Check input fields.");
    }
  }

  async function askPatientHistoryQuestion(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedId || !patientQuestion.trim()) return;
    setAskLoading(true);
    setPatientAnswer(null);

    try {
      const login = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "CLINICIAN-DEMO", role: "ATTENDING_PHYSICIAN" }),
      });
      const auth = await login.json();

      const res = await fetch(`/api/patients/${selectedId}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${auth.access_token}`,
        },
        body: JSON.stringify({ question: patientQuestion.trim() }),
      });
      if (res.ok) {
        setPatientAnswer(await res.json());
      }
    } catch {
      // Keep silent
    } finally {
      setAskLoading(false);
    }
  }

  const patient = history?.patient;
  const previousVisit = history?.visits && history.visits.length > 0 ? history.visits[0] : null;

  return (
    <main className="dashboard-page">
      {/* SYNTHETIC DEMONSTRATION DATA BANNER */}
      <div className="synthetic-data-banner">
        SYNTHETIC DEMONSTRATION DATA — NOT REAL PATIENT DATA
      </div>

      <header className="dashboard-header">
        <div>
          <p className="dashboard-kicker">ANTIBIOTIX CLINICAL DECISION SUPPORT SYSTEM</p>
          <h1>Doctor Patient Record & Prescription Memory</h1>
          <p className="dashboard-subtitle">
            Longitudinal Patient History · 24 Deterministic Rules · Grounded RAG History Assistant
          </p>
        </div>
        <Link href="/" className="dashboard-exit">
          Exit workspace <X size={15} />
        </Link>
      </header>

      {/* DOCTOR NAVIGATION BAR */}
      <nav className="doctor-nav-bar">
        <button
          className={`doctor-nav-tab ${activeTab === "dashboard" ? "active" : ""}`}
          onClick={() => setActiveTab("dashboard")}
        >
          <LayoutDashboard size={15} /> Dashboard
        </button>
        <button
          className={`doctor-nav-tab ${activeTab === "patient" ? "active" : ""}`}
          onClick={() => setActiveTab("patient")}
        >
          <UserRound size={15} /> Patient Profile {selectedId ? `(${selectedId})` : ""}
        </button>
        <button
          className={`doctor-nav-tab ${activeTab === "new_visit" ? "active" : ""}`}
          onClick={() => {
            if (!selectedId && patients.length > 0) setSelectedId(patients[0].patient_id);
            setActiveTab("new_visit");
          }}
        >
          <Plus size={15} /> Start New Visit
        </button>
        <button
          className={`doctor-nav-tab ${activeTab === "medications" ? "active" : ""}`}
          onClick={() => setActiveTab("medications")}
        >
          <Pill size={15} /> Medication History
        </button>
        <Link href="/clinical-tools" className="doctor-nav-tab">
          <Wrench size={15} /> Clinical Tools
        </Link>
      </nav>

      <div className="dashboard-layout">
        {/* SIDEBAR PATIENT ROSTER */}
        <aside className="dashboard-sidebar">
          <div className="dashboard-section-heading">
            <div>
              <p className="dashboard-kicker">PATIENT ROSTER</p>
              <h2>Select Patient</h2>
            </div>
            <span className="record-count">{patients.length} records</span>
          </div>

          <div style={{ margin: "12px 0" }}>
            <input
              type="text"
              placeholder="Search patient ID or name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="dashboard-select"
            />
          </div>

          <div className="mode-switch" role="tablist">
            <button className={mode === "returning" ? "selected" : ""} onClick={() => setMode("returning")}>
              <History size={14} /> Returning
            </button>
            <button className={mode === "new" ? "selected" : ""} onClick={() => setMode("new")}>
              <Plus size={14} /> Register New
            </button>
          </div>

          {mode === "returning" ? (
            <>
              <label className="field-label" htmlFor="patient-picker">Patient</label>
              <select
                id="patient-picker"
                className="dashboard-select"
                value={selectedId}
                onChange={(e) => {
                  setSelectedId(e.target.value);
                  void loadHistory(e.target.value);
                }}
              >
                <option value="">Select a patient</option>
                {patients.map((item) => (
                  <option key={item.patient_id} value={item.patient_id}>
                    {patientName(item.display_name, item.patient_id)} · {item.patient_id} · {display(item.age)} yrs · {display(item.sex)}
                  </option>
                ))}
              </select>

              {presets.length > 0 && (
                <div className="quick-presets-section">
                  <span className="field-label">Quick Teaching Scenarios ({presets.length})</span>
                  <div className="preset-chips-scroll">
                    {presets.map((p) => (
                      <button
                        key={p.key}
                        type="button"
                        className={`preset-chip ${selectedId === p.patient_id ? "active" : ""}`}
                        onClick={() => {
                          setSelectedId(p.patient_id);
                          void loadHistory(p.patient_id);
                        }}
                      >
                        {/* The scenario endpoint carries no name of its own, so it
                            is looked up from the roster loaded alongside it; a miss
                            falls back to the id rather than rendering blank. */}
                        <span className="preset-chip-id">
                          {patientName(
                            patients.find((pat) => pat.patient_id === p.patient_id)?.display_name,
                            p.patient_id,
                          )}
                        </span>
                        <span className="preset-chip-title">{p.diagnosis}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <form className="registration-form" onSubmit={registerPatient}>
              <label className="field-label">Patient Full Name (e.g. Rajesh Sharma) *</label>
              <input type="text" placeholder="Enter patient name..." value={regForm.name} onChange={(e) => setRegForm({ ...regForm, name: e.target.value })} />

              <label className="field-label">Age *</label>
              <input type="number" min="0" max="125" value={regForm.age} onChange={(e) => setRegForm({ ...regForm, age: e.target.value })} />

              <label className="field-label">Sex *</label>
              <select value={regForm.sex} onChange={(e) => setRegForm({ ...regForm, sex: e.target.value })}>
                <option value="UNKNOWN">Select</option>
                <option value="FEMALE">Female</option>
                <option value="MALE">Male</option>
              </select>

              <label className="field-label">Initial Diagnosis *</label>
              <input value={regForm.diagnosis} onChange={(e) => setRegForm({ ...regForm, diagnosis: e.target.value })} />

              <label className="field-label">Weight (kg)</label>
              <input type="number" value={regForm.weight} onChange={(e) => setRegForm({ ...regForm, weight: e.target.value })} />

              <label className="field-label">Renal eGFR</label>
              <input type="number" value={regForm.egfr} onChange={(e) => setRegForm({ ...regForm, egfr: e.target.value })} />

              <label className="field-label">Allergies</label>
              <input placeholder="Penicillin, Sulfonamides" value={regForm.allergies} onChange={(e) => setRegForm({ ...regForm, allergies: e.target.value })} />

              <label className="field-label">Medical History</label>
              <input placeholder="Hypertension, Asthma" value={regForm.medicalHistory} onChange={(e) => setRegForm({ ...regForm, medicalHistory: e.target.value })} />

              <label className="field-label">Current Medications</label>
              <textarea rows={2} value={regForm.medications} onChange={(e) => setRegForm({ ...regForm, medications: e.target.value })} />

              {formError && <p className="form-error">{formError}</p>}
              <button className="dashboard-button primary" type="submit" style={{ marginTop: "12px", width: "100%" }}>
                Register Patient <ArrowRight size={15} />
              </button>
            </form>
          )}
        </aside>

        {/* MAIN DASHBOARD CONTENT AREA */}
        <div className="dashboard-main">
          {/* 1. DASHBOARD OVERVIEW TAB */}
          {activeTab === "dashboard" && (
            <>
              <div className="dashboard-stats-grid">
                <div className="stat-card">
                  <span className="stat-label">Total Patients</span>
                  <span className="stat-value">{stats?.total_patients || patients.length}</span>
                  <span className="stat-sub">Structured DB Records</span>
                </div>
                <div className="stat-card">
                  <span className="stat-label">Total Visits</span>
                  <span className="stat-value">{stats?.total_visits || 0}</span>
                  <span className="stat-sub">Immutable History Events</span>
                </div>
                <div className="stat-card">
                  <span className="stat-label">Prescriptions</span>
                  <span className="stat-value">{stats?.total_prescriptions || 0}</span>
                  <span className="stat-sub">Stored & Indexed</span>
                </div>
                <div className="stat-card">
                  <span className="stat-label">Active Safety Warnings</span>
                  <span className="stat-value" style={{ color: stats?.critical_warnings_count ? "#a33d31" : "#173c3d" }}>
                    {stats?.total_active_warnings || 0}
                  </span>
                  <span className="stat-sub">{ruleEngineLabel(ruleCount)} Alerts</span>
                </div>
              </div>

              <section className="info-section">
                <div className="section-title-row">
                  <div>
                    <p className="dashboard-kicker">DOCTOR WORKSPACE</p>
                    <h2>Recent Patients & Clinical Status</h2>
                  </div>
                  <button className="dashboard-button primary" onClick={() => setMode("new")}>
                    <Plus size={15} /> Register New Patient
                  </button>
                </div>

                <table className="patient-table">
                  <thead>
                    <tr>
                      <th>Patient ID</th>
                      <th>Display Name</th>
                      <th>Age / Sex</th>
                      <th>Last Visit</th>
                      <th>Last Diagnosis</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {patients.map((p) => (
                      <tr key={p.patient_id} onClick={() => selectPatient(p.patient_id, "patient")}>
                        <td><strong>{p.patient_id}</strong></td>
                        {/* Through the helper, not raw: a record seeded before
                            display_name held a bare name carries "PATIENT-001
                            (Rajesh Sharma)", which printed the id twice on this row. */}
                        <td>{patientName(p.display_name, p.patient_id)}</td>
                        <td>{display(p.age)} yrs · {display(p.sex)}</td>
                        <td>{p.last_visit || "No visits"}</td>
                        <td>{p.last_diagnosis || "None recorded"}</td>
                        <td>
                          <button
                            className="dashboard-button secondary"
                            style={{ padding: "4px 10px", fontSize: "0.72rem" }}
                            onClick={(e) => {
                              e.stopPropagation();
                              selectPatient(p.patient_id, "new_visit");
                            }}
                          >
                            New Visit
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          )}

          {/* 2. PATIENT PROFILE & LONGITUDINAL HISTORY TAB */}
          {(activeTab === "patient" || activeTab === "medications") && (
            <>
              {!patient ? (
                <div className="dashboard-empty">Select a patient to view longitudinal record</div>
              ) : (
                <>
                  <section className="current-banner">
                    <div>
                      <p className="dashboard-kicker">PATIENT PROFILE</p>
                      <h2>{patientName(patient.display_name, patient.patient_id)} ({patient.patient_id})</h2>
                      <p>
                        {display(patient.age)} years · {display(patient.sex)} · {display(patient.weight_kg)} kg · eGFR {display(patient.egfr_ml_min)} mL/min
                      </p>
                    </div>
                    <div style={{ display: "flex", gap: "8px" }}>
                      <button className="dashboard-button primary" onClick={() => selectPatient(patient.patient_id, "new_visit")}>
                        <Plus size={15} /> Start New Visit
                      </button>
                    </div>
                  </section>

                  {/* CLINICAL CONTEXT GRID */}
                  <section className="info-section">
                    <div className="section-title-row">
                      <div>
                        <p className="dashboard-kicker">LONGITUDINAL RECORD</p>
                        <h2>Patient Demographics & Medical Profile</h2>
                      </div>
                    </div>
                    <div className="context-grid">
                      <div>
                        <span>Documented Allergies</span>
                        <strong>{patient.allergies?.join(", ") || "None documented"}</strong>
                      </div>
                      <div>
                        <span>Current Medications</span>
                        <strong>{patient.active_medications?.join(", ") || "None recorded"}</strong>
                      </div>
                      <div>
                        <span>Medical History</span>
                        <strong>{patient.medical_history?.join(", ") || "No prior history"}</strong>
                      </div>
                      <div>
                        <span>Renal Status</span>
                        <strong>{patient.renal_status_known ? `${display(patient.egfr_ml_min)} mL/min` : "Not assessed"}</strong>
                      </div>
                      <div>
                        <span>Hepatic Status</span>
                        <strong>{patient.hepatic_status_known ? display(patient.child_pugh_class || "Normal") : "Not assessed"}</strong>
                      </div>
                      <div>
                        <span>Pregnancy / Lactation</span>
                        <strong>{display(patient.pregnancy_status)} / {display(patient.lactation_status)}</strong>
                      </div>
                    </div>
                  </section>

                  {/* DEDICATED MEDICATION HISTORY TAB */}
                  {activeTab === "medications" ? (
                    <section className="info-section">
                      <div className="section-title-row">
                        <div>
                          <p className="dashboard-kicker">PRESCRIPTION MEMORY</p>
                          <h2>Medication History View</h2>
                        </div>
                      </div>
                      <table className="patient-table">
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th>Visit ID</th>
                            <th>Diagnosis</th>
                            <th>Medication</th>
                            <th>Dose / Route</th>
                            <th>Frequency</th>
                            <th>Duration</th>
                          </tr>
                        </thead>
                        <tbody>
                          {history?.visits.flatMap((v) =>
                            v.medications.map((m, idx) => (
                              <tr key={`${v.visit_id}-${idx}`}>
                                <td>{formatDate(v.visit_date)}</td>
                                <td><strong>{v.visit_id}</strong></td>
                                <td>{v.diagnosis}</td>
                                <td><strong>{m.name}</strong></td>
                                <td>{m.dose ? `${m.dose} ${m.unit || ""}` : ""} {m.route || ""}</td>
                                <td>{m.frequency || "TID"}</td>
                                <td>{m.duration_days ? `${m.duration_days} days` : "5 days"}</td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </section>
                  ) : (
                    /* CHRONOLOGICAL VISIT HISTORY TIMELINE */
                    <section className="info-section history-section">
                      <div className="section-title-row">
                        <div>
                          <p className="dashboard-kicker">IMMUTABLE HISTORICAL EVENTS</p>
                          <h2>Visit History Timeline ({history?.visits.length || 0} visits)</h2>
                        </div>
                      </div>
                      {history?.visits.length ? (
                        <div className="timeline">
                          {history.visits.map((visit) => {
                            const isHighlighted = highlightedVisitId === visit.visit_id;
                            return (
                              <article
                                className="timeline-item"
                                key={visit.visit_id}
                                style={isHighlighted ? { background: "#eef8f3", padding: "12px", borderRadius: "6px", border: "2px solid #2d7064" } : {}}
                              >
                                <span className="timeline-dot" />
                                <div>
                                  <time>{formatDate(visit.visit_date)} · <strong>Visit {visit.visit_id}</strong></time>
                                  <h3>{display(visit.diagnosis)}</h3>
                                  
                                  {visit.symptoms && visit.symptoms.length > 0 && (
                                    <p>
                                      <b>Symptoms:</b> {visit.symptoms.map((s) => `${s.name} (${s.severity || "Moderate"}, ${s.duration || "3 days"})`).join(", ")}
                                    </p>
                                  )}

                                  <p>
                                    <b>Prescription:</b>{" "}
                                    {visit.medications.map((m) => `${m.name} ${m.dose ? `${m.dose}${m.unit || ""}` : ""} ${m.frequency || ""}`).join(" · ") || "No medication recorded"}
                                  </p>

                                  {visit.findings.length > 0 && (
                                    <p className="finding-note">
                                      <FileWarning size={14} /> {visit.findings.length} safety finding(s) surfaced by 24-rule engine
                                    </p>
                                  )}

                                  <details className="visit-details" open={isHighlighted}>
                                    <summary style={{ cursor: "pointer", color: "#2d7064", fontWeight: 600 }}>View full visit details</summary>
                                    <p><b>Clinical notes:</b> {display(visit.clinical_notes)}</p>
                                    <p><b>Safety findings:</b> {visit.findings.map((f) => `${f.severity || ""}: ${f.title || f.clinical_concern}`).join(" · ") || "None"}</p>
                                    <p><b>Clinician overrides:</b> {visit.overrides.map((o) => `${o.clinician_role}: ${o.reason}`).join(" · ") || "None"}</p>
                                  </details>
                                  <small>Attending Clinician: {display(visit.clinician_id)}</small>
                                </div>
                              </article>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="muted">No previous visits. Click Start New Visit to record the initial visit.</p>
                      )}
                    </section>
                  )}

                  {/* ASK ABOUT THIS PATIENT RAG ASSISTANT */}
                  <section className="ask-assistant-box">
                    <div className="section-title-row">
                      <div>
                        <p className="dashboard-kicker">HYBRID PATIENT RAG RETRIEVAL</p>
                        <h2>Ask About This Patient's History</h2>
                      </div>
                      <BookOpenCheck size={20} color="#2d7064" />
                    </div>
                    <p style={{ fontSize: "0.78rem", color: "#607371", margin: "4px 0 10px" }}>
                      Ask natural language questions. Answers are grounded EXCLUSIVELY in <strong>{patientName(patient.display_name, patient.patient_id)}</strong>'s stored records with strict patient isolation.
                    </p>

                    <div className="example-chips">
                      <button className="example-chip" onClick={() => setPatientQuestion("What was the diagnosis during his last visit?")}>
                        "What was the diagnosis during his last visit?"
                      </button>
                      <button className="example-chip" onClick={() => setPatientQuestion("What medications has this patient previously received?")}>
                        "What medications has he received?"
                      </button>
                      <button className="example-chip" onClick={() => setPatientQuestion("What symptoms did he have during his previous visit?")}>
                        "What symptoms during previous visit?"
                      </button>
                      <button className="example-chip" onClick={() => setPatientQuestion("When did he last visit?")}>
                        "When did he last visit?"
                      </button>
                    </div>

                    <form className="ask-input-row" onSubmit={askPatientHistoryQuestion}>
                      <input
                        type="text"
                        placeholder="Ask a question about this patient's history..."
                        value={patientQuestion}
                        onChange={(e) => setPatientQuestion(e.target.value)}
                      />
                      <button className="dashboard-button primary" type="submit" disabled={askLoading}>
                        {askLoading ? "Searching..." : "Ask Patient History"}
                      </button>
                    </form>

                    {patientAnswer && (
                      <div className="ask-answer-card">
                        <pre>{patientAnswer.answer}</pre>
                        {patientAnswer.source_visit_id && (
                          <div
                            className="source-citation-link"
                            onClick={() => {
                              setActiveTab("patient");
                              setHighlightedVisitId(patientAnswer.source_visit_id);
                            }}
                          >
                            Source: Visit {patientAnswer.source_visit_id} (Click to open visit in timeline)
                          </div>
                        )}
                      </div>
                    )}
                  </section>
                </>
              )}
            </>
          )}

          {/* 3. NEW VISIT WORKFLOW TAB */}
          {activeTab === "new_visit" && (
            <section className="info-section">
              <div className="section-title-row">
                <div>
                  <p className="dashboard-kicker">NEW IMMUTABLE VISIT</p>
                  <h2>Start New Visit for Patient {selectedId}</h2>
                </div>
              </div>

              {/* PREVIOUS VISIT CONTEXT PANEL */}
              {previousVisit ? (
                <div className="previous-visit-panel">
                  <h4>Relevant Previous History (Visit {previousVisit.visit_id} - {formatDate(previousVisit.visit_date)})</h4>
                  <p style={{ margin: "2px 0", fontSize: "0.82rem" }}>
                    <b>Previous Diagnosis:</b> {display(previousVisit.diagnosis)}
                  </p>
                  <p style={{ margin: "2px 0", fontSize: "0.82rem" }}>
                    <b>Previous Medications:</b>{" "}
                    {previousVisit.medications.map((m) => `${m.name} ${m.dose ? `${m.dose}${m.unit || ""}` : ""} ${m.frequency || ""}`).join(" · ") || "None"}
                  </p>
                  <p style={{ margin: "2px 0", fontSize: "0.82rem" }}>
                    <b>Documented Allergies:</b> {patient?.allergies?.join(", ") || "None"}
                  </p>
                </div>
              ) : (
                <div className="previous-visit-panel">
                  <h4>Initial Visit Record</h4>
                  <p style={{ margin: 0, fontSize: "0.82rem" }}>This will be the patient's first recorded historical visit.</p>
                </div>
              )}

              <form onSubmit={saveVisit}>
                <div style={{ display: "grid", gap: "14px" }}>
                  <div>
                    <label className="field-label">Current Diagnosis *</label>
                    <input
                      type="text"
                      placeholder="e.g. Community-acquired pneumonia"
                      value={newVisitDiagnosis}
                      onChange={(e) => setNewVisitDiagnosis(e.target.value)}
                    />
                  </div>

                  {/* STRUCTURED SYMPTOMS INPUT */}
                  <div>
                    <label className="field-label">Record Current Symptoms</label>
                    <div style={{ display: "flex", gap: "8px" }}>
                      <input
                        type="text"
                        placeholder="Symptom name (e.g. Fever, Cough)"
                        value={symName}
                        onChange={(e) => setSymName(e.target.value)}
                        style={{ flex: 2 }}
                      />
                      <select value={symSeverity} onChange={(e) => setSymSeverity(e.target.value)} style={{ flex: 1 }}>
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
                      />
                      <button type="button" className="dashboard-button secondary" onClick={addSymptom}>
                        Add Symptom
                      </button>
                    </div>

                    {symptomsList.length > 0 && (
                      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "10px" }}>
                        {symptomsList.map((s, idx) => (
                          <span className="symptom-tag" key={idx}>
                            {s.name} ({s.severity}, {s.duration})
                            <X size={12} style={{ cursor: "pointer" }} onClick={() => removeSymptom(idx)} />
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="field-label">Clinical Notes</label>
                    <textarea
                      rows={2}
                      placeholder="Enter clinical examination notes and context..."
                      value={newVisitNotes}
                      onChange={(e) => setNewVisitNotes(e.target.value)}
                    />
                  </div>

                  {/* PRESCRIPTION MODULE */}
                  <div style={{ borderTop: "1px solid #d8e2dd", paddingTop: "14px", marginTop: "10px" }}>
                    <p className="dashboard-kicker">PRESCRIPTION MODULE</p>
                    <h3>Prescribe Medications for Current Visit</h3>

                    <label className="field-label">Add Structured Medication</label>
                    <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                      <input placeholder="Drug name (e.g. Amoxicillin)" value={medName} onChange={(e) => setMedName(e.target.value)} style={{ flex: 2 }} />
                      <input placeholder="Dose" type="number" value={medDose} onChange={(e) => setMedDose(e.target.value)} style={{ width: "80px" }} />
                      <select value={medUnit} onChange={(e) => setMedUnit(e.target.value)} style={{ width: "70px" }}>
                        <option value="mg">mg</option>
                        <option value="g">g</option>
                        <option value="mcg">mcg</option>
                      </select>
                      <select value={medRoute} onChange={(e) => setMedRoute(e.target.value)} style={{ width: "70px" }}>
                        <option value="PO">PO</option>
                        <option value="IV">IV</option>
                        <option value="IM">IM</option>
                      </select>
                      <select value={medFreq} onChange={(e) => setMedFreq(e.target.value)} style={{ width: "80px" }}>
                        <option value="QD">QD</option>
                        <option value="BID">BID</option>
                        <option value="TID">TID</option>
                        <option value="QID">QID</option>
                      </select>
                      <input placeholder="Days" type="number" value={medDur} onChange={(e) => setMedDur(e.target.value)} style={{ width: "70px" }} />
                      <button type="button" className="dashboard-button secondary" onClick={addMedication}>
                        Add Medication
                      </button>
                    </div>

                    {prescriptionItems.length > 0 && (
                      <div style={{ marginTop: "10px" }}>
                        <strong>Prescribed Items:</strong>
                        <ul style={{ margin: "6px 0", paddingLeft: "20px" }}>
                          {prescriptionItems.map((item, idx) => (
                            <li key={idx}>
                              {item.medication_name} {item.dose} {item.unit} {item.route} {item.frequency} for {item.duration_days} days{" "}
                              <X size={12} style={{ cursor: "pointer", color: "#a33d31" }} onClick={() => removeMedication(idx)} />
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div style={{ marginTop: "12px" }}>
                      <button type="button" className="dashboard-button warning" onClick={runSafetyAnalysis}>
                        <ShieldCheck size={16} /> Run AntiBioTix {ruleEngineLabel(ruleCount)} Safety Analysis
                      </button>
                    </div>

                    {analysisStatus && <p className="muted" style={{ marginTop: "8px" }}>{analysisStatus}</p>}

                    {/* DISPLAY SAFETY WARNINGS FROM 24-RULE ENGINE */}
                    {safetyWarnings.length > 0 && (
                      <div style={{ marginTop: "14px", display: "grid", gap: "10px" }}>
                        {safetyWarnings.map((w, idx) => (
                          <div key={idx} style={{ background: "#fdf2f0", borderLeft: "4px solid #a33d31", padding: "12px", borderRadius: "4px" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <strong style={{ color: "#a33d31" }}>[{w.severity}] {w.title}</strong>
                              <span style={{ fontSize: "0.7rem", color: "#718281" }}>Rule: {w.rule_id}</span>
                            </div>
                            <p style={{ margin: "4px 0", fontSize: "0.8rem" }}>{w.clinical_concern}</p>
                            <p style={{ margin: "4px 0", fontSize: "0.8rem", fontWeight: 600 }}>Recommendation: {w.recommendation}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {formError && <p className="form-error">{formError}</p>}
                  {visitSavedMsg && <p className="form-intro" style={{ color: "#2d7064", fontWeight: 700 }}>{visitSavedMsg}</p>}

                  <div style={{ marginTop: "16px", display: "flex", gap: "10px" }}>
                    <button className="dashboard-button primary" type="submit">
                      Save Completed Visit & Index for RAG <CheckCircle2 size={16} />
                    </button>
                    <button className="dashboard-button secondary" type="button" onClick={() => setActiveTab("patient")}>
                      Cancel
                    </button>
                  </div>
                </div>
              </form>
            </section>
          )}
        </div>
      </div>
    </main>
  );
}
