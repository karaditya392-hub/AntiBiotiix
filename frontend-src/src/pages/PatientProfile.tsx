import { useEffect, useState } from "react";
import { ArrowLeft, BookOpenCheck, FileWarning, Pill, Plus } from "lucide-react";
import { Link, useLocation, useParams } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import "@/styles/patient-dashboard.css";
import { patientName } from "@/lib/patient";

type Patient = {
  patient_id: string;
  display_name?: string;
  age?: number;
  sex?: string;
  weight_kg?: number;
  allergies?: string[];
  medical_history?: string[];
  egfr_ml_min?: number;
  renal_status_known?: boolean;
  child_pugh_class?: string;
  hepatic_status_known?: boolean;
  pregnancy_status?: string;
  lactation_status?: string;
  active_medications?: string[];
  clinical_notes?: string;
};

type Visit = {
  visit_id: string;
  prescription_id?: string;
  visit_date: string;
  diagnosis?: string;
  clinical_notes?: string;
  clinician_id?: string;
  symptoms?: Array<Record<string, string>>;
  medications: Array<Record<string, any>>;
  findings: Array<Record<string, string>>;
  overrides: Array<Record<string, string>>;
};

type HistoryData = {
  patient: Patient;
  visits: Visit[];
};

function formatVisitDate(v: any): string {
  if (v?.formatted_date) return v.formatted_date;
  if (!v?.visit_date) return "Not recorded";
  try {
    const d = new Date(v.visit_date);
    if (isNaN(d.getTime())) return String(v.visit_date);
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
    return String(v.visit_date);
  }
}

export default function PatientProfile() {
  const { patient_id } = useParams<{ patient_id: string }>();
  const [, setLocation] = useLocation();
  const [data, setData] = useState<HistoryData | null>(null);
  const [nextAppointment, setNextAppointment] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  async function loadPatientProfile() {
    if (!patient_id) return;
    try {
      const [histRes, apptRes] = await Promise.all([
        fetch(`/api/patients/${encodeURIComponent(patient_id)}/history`),
        fetch(`/api/patients/${encodeURIComponent(patient_id)}/next-appointment`),
      ]);
      if (histRes.ok) setData(await histRes.json());
      if (apptRes.ok) setNextAppointment(await apptRes.json());
    } catch {
      // Keep state
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPatientProfile();
  }, [patient_id]);

  if (loading) {
    return (
      <main className="dashboard-page">
        <div className="dashboard-empty">Loading patient profile...</div>
      </main>
    );
  }

  if (!data?.patient) {
    return (
      <main className="dashboard-page">
        <div className="dashboard-empty">
          <h2>Patient record not found</h2>
          <Link href="/patients/returning" className="dashboard-button primary">
            Back to Patient Selection
          </Link>
        </div>
      </main>
    );
  }

  const patient = data.patient;

  return (
    <main className="dashboard-page">
      <UnifiedHeader />

      <div className="dashboard-header" style={{ marginBottom: "16px" }}>
        <div>
          <p className="dashboard-kicker">PATIENT PROFILE & LONGITUDINAL RECORD</p>
          <h1>{patientName(patient.display_name, patient.patient_id)}</h1>
          <p className="dashboard-subtitle">
            {patient.age ?? "Unknown"} years · {patient.sex || "Sex unrecorded"} · {patient.weight_kg ?? "Unrecorded"} kg · eGFR {patient.egfr_ml_min ?? "Not assessed"} mL/min
          </p>
        </div>
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
          <button
            className="dashboard-button primary"
            onClick={() => setLocation(`/patients/${patient.patient_id}/visit/new`)}
          >
            <Plus size={16} /> Start New Visit
          </button>
          <button
            className="dashboard-button secondary"
            onClick={() => setLocation(`/patients/${patient.patient_id}/medications`)}
          >
            <Pill size={16} /> Medication History
          </button>
          <button
            className="dashboard-button secondary"
            onClick={() => setLocation(`/patients/${patient.patient_id}/history-assistant`)}
          >
            <BookOpenCheck size={16} /> Ask About Patient
          </button>
          <Link href="/patients/returning" className="dashboard-button secondary">
            <ArrowLeft size={15} /> Back to Selection
          </Link>
        </div>
      </div>

      {/* AUTOMATED CHECK-UP NOTIFICATION BANNER */}
      {nextAppointment?.has_appointment && (
        <section
          className="info-section"
          style={{
            marginBottom: "20px",
            background: nextAppointment.is_today ? "#fbe9e5" : "#eef8f3",
            borderColor: nextAppointment.is_today ? "#a65e38" : "#2d7064",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <p
                className="dashboard-kicker"
                style={{ color: nextAppointment.is_today ? "#a65e38" : "#2d7064" }}
              >
                {nextAppointment.is_today
                  ? "NOTIFICATION ALERT: CHECK-UP SCHEDULED FOR TODAY (IST)"
                  : "NEXT UPCOMING CHECK-UP (IST)"}
              </p>
              <h2 style={{ margin: "2px 0", color: "#173c3d", fontSize: "1.15rem" }}>
                {nextAppointment.formatted_date_ist}
              </h2>
              <p style={{ margin: "4px 0 0", fontSize: "0.84rem", color: "#526968" }}>
                <b>Reason:</b> {nextAppointment.reason} · <b>Attending Doctor:</b> {nextAppointment.doctor_id} ·{" "}
                <b>Multi-channel Alerts:</b> Email ({nextAppointment.doctor_email}), SMS ({nextAppointment.patient_phone})
              </p>
            </div>
            {nextAppointment.is_today && (
              <button
                className="dashboard-button primary"
                onClick={() => setLocation(`/patients/${patient.patient_id}/visit/new`)}
              >
                Start Check-up Visit
              </button>
            )}
          </div>
        </section>
      )}

      {/* DEMOGRAPHICS & CLINICAL FACTORS GRID */}
      <section className="info-section" style={{ marginBottom: "20px" }}>
        <div className="section-title-row">
          <div>
            <p className="dashboard-kicker">RECORDED CLINICAL FACTORS</p>
            <h2>Patient Clinical Summary</h2>
          </div>
        </div>
        <div className="context-grid">
          <div>
            <span>Documented Allergies</span>
            <strong>{patient.allergies?.join(", ") || "None documented"}</strong>
          </div>
          <div>
            <span>Current Home Medications</span>
            <strong>{patient.active_medications?.join(", ") || "None recorded"}</strong>
          </div>
          <div>
            <span>Medical History</span>
            <strong>{patient.medical_history?.join(", ") || "No historical conditions"}</strong>
          </div>
          <div>
            <span>Renal Function (eGFR)</span>
            <strong>{patient.renal_status_known ? `${patient.egfr_ml_min} mL/min` : "Not assessed"}</strong>
          </div>
          <div>
            <span>Hepatic Status</span>
            <strong>{patient.hepatic_status_known ? (patient.child_pugh_class || "Normal") : "Not assessed"}</strong>
          </div>
          <div>
            <span>Pregnancy / Lactation</span>
            <strong>{patient.pregnancy_status || "Unknown"} / {patient.lactation_status || "Unknown"}</strong>
          </div>
        </div>
      </section>

      {/* CHRONOLOGICAL VISIT TIMELINE */}
      <section className="info-section history-section">
        <div className="section-title-row">
          <div>
            <p className="dashboard-kicker">IMMUTABLE VISITS</p>
            <h2>Chronological Visit History ({data.visits.length} visits)</h2>
          </div>
        </div>

        {data.visits.length === 0 ? (
          <p className="muted" style={{ padding: "14px 0" }}>
            No previous visits recorded for this patient. Click Start New Visit to create their first visit.
          </p>
        ) : (
          <div className="timeline">
            {data.visits.map((v) => (
              <article className="timeline-item" key={v.visit_id}>
                <span className="timeline-dot" />
                <div>
                  <time>{formatVisitDate(v)} · <strong>Visit {v.visit_id}</strong></time>
                  <h3>{v.diagnosis || "No diagnosis recorded"}</h3>

                  {v.symptoms && v.symptoms.length > 0 && (
                    <p>
                      <b>Symptoms:</b> {v.symptoms.map((s) => `${s.name} (${s.severity || "Moderate"}, ${s.duration || "3 days"})`).join(", ")}
                    </p>
                  )}

                  <p>
                    <b>Prescription:</b>{" "}
                    {v.medications.map((m) => `${m.name} ${m.dose ? `${m.dose}${m.unit || ""}` : ""} ${m.frequency || ""}`).join(" · ") || "No medication recorded"}
                  </p>

                  {v.findings.length > 0 && (
                    <p className="finding-note">
                      <FileWarning size={14} /> {v.findings.length} safety warning(s) evaluated by 30-rule engine
                    </p>
                  )}

                  <details className="visit-details" style={{ marginTop: "6px" }}>
                    <summary style={{ cursor: "pointer", color: "#2d7064", fontWeight: 600 }}>View full visit details</summary>
                    <p><b>Clinical Notes:</b> {v.clinical_notes || "None recorded"}</p>
                    <p><b>Safety Warnings:</b> {v.findings.map((f) => `${f.severity}: ${f.title || f.clinical_concern}`).join(" · ") || "None"}</p>
                    <p><b>Clinician Overrides:</b> {v.overrides.map((o) => `${o.clinician_role}: ${o.reason}`).join(" · ") || "None"}</p>
                  </details>
                  <small style={{ marginTop: "4px", display: "block" }}>Clinician ID: {v.clinician_id || "DOC-DEMO-01"}</small>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
