import { useEffect, useState } from "react";
import { ArrowLeft, BookOpenCheck, FileWarning, Pill, Plus } from "lucide-react";
import { Link, useLocation, useParams } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import "@/styles/patient-dashboard.css";
import { patientName } from "@/lib/patient";
import { useAuth } from "@/context/AuthContext";

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

// How an adherence answer reads to a clinician.
//
// STOPPED and SOME are called out because they change what happens next: a course
// abandoned halfway is both a treatment failure risk and a resistance driver, and
// it is invisible everywhere else in this system -- the prescription records what
// was ordered, never what was swallowed.
const DOSE_LABELS: Record<string, { text: string; alarming: boolean }> = {
  ALL: { text: "took every dose", alarming: false },
  MOST: { text: "missed a few doses", alarming: false },
  SOME: { text: "took only some doses", alarming: true },
  STOPPED: { text: "has STOPPED taking it", alarming: true },
};

export default function PatientProfile() {
  const { patient_id } = useParams<{ patient_id: string }>();
  const { token } = useAuth();
  const [, setLocation] = useLocation();
  const [data, setData] = useState<HistoryData | null>(null);
  const [nextAppointment, setNextAppointment] = useState<any>(null);
  // What this patient has reported since their visit. Loaded here because the
  // post-login alert links straight to this page.
  const [feedback, setFeedback] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  async function loadPatientProfile() {
    if (!patient_id) return;
    try {
      const [histRes, apptRes, fbRes] = await Promise.all([
        fetch(`/api/patients/${encodeURIComponent(patient_id)}/history`),
        fetch(`/api/patients/${encodeURIComponent(patient_id)}/next-appointment`),
        // Scoped to this patient by the server, not filtered client-side.
        fetch(`/api/feedback?patient_id=${encodeURIComponent(patient_id)}`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);
      if (histRes.ok) setData(await histRes.json());
      if (apptRes.ok) setNextAppointment(await apptRes.json());
      if (fbRes.ok) setFeedback((await fbRes.json()).responses || []);
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

      {/*
        WHAT THIS PATIENT REPORTED.

        Placed above the appointment banner and the record, because this is where
        the post-login alert lands: a clinician who clicked "Rajesh Sharma reports
        feeling worse" is here to read that, and should not have to hunt for it.
      */}
      {feedback.length > 0 && (
        <section className="info-section" style={{ marginBottom: "20px" }}>
          <div className="section-title-row" style={{ marginBottom: "10px" }}>
            <div>
              <p className="dashboard-kicker">PATIENT FOLLOW-UP</p>
              <h2>What {patientName(patient.display_name, patient.patient_id)} reported</h2>
            </div>
          </div>
          <div style={{ display: "grid", gap: "8px" }}>
            {feedback.map((f: any) => {
              const worse = f.feeling === "WORSE";
              return (
                <div
                  key={f.response_id}
                  style={{
                    background: worse ? "#fbe9e5" : "#f0f6f1",
                    border: `1px solid ${worse ? "#e3b9b0" : "#d0e2d8"}`,
                    borderLeft: `4px solid ${worse ? "#a33d31" : "#2d7064"}`,
                    borderRadius: "6px", padding: "10px 12px", fontSize: "0.82rem",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "10px" }}>
                    <strong style={{ color: worse ? "#a33d31" : "#173c3d" }}>
                      {worse ? "Reported feeling worse"
                        : f.feeling === "SAME" ? "Reported no change"
                        : "Reported feeling better"}
                    </strong>
                    <span className="muted" style={{ fontSize: "0.72rem" }}>
                      {f.visit_id} · {f.submitted_at ? new Date(f.submitted_at).toLocaleString() : "date not recorded"}
                    </span>
                  </div>
                  <div style={{ marginTop: "4px", color: "#203236" }}>
                    Medicines helped: <b>{(f.medicines_helped || "not answered").toLowerCase()}</b>
                  </div>
                  {DOSE_LABELS[f.doses_taken] && (
                    <div style={{
                      marginTop: "4px",
                      color: DOSE_LABELS[f.doses_taken].alarming ? "#a33d31" : "#526968",
                      fontWeight: DOSE_LABELS[f.doses_taken].alarming ? 600 : 400,
                    }}>
                      Doses: {DOSE_LABELS[f.doses_taken].text}
                    </div>
                  )}
                  {f.discomfort && (
                    /* The patient's own words, unedited. */
                    <div style={{ marginTop: "4px", color: "#526968" }}>“{f.discomfort}”</div>
                  )}
                </div>
              );
            })}
          </div>
          <p className="muted" style={{ fontSize: "0.72rem", margin: "8px 0 0" }}>
            Submitted by the patient through the follow-up link. Recorded as given and
            not clinically assessed by this system.
          </p>
        </section>
      )}

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
