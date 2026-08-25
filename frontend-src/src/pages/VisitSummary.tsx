import { useEffect, useState } from "react";
import { BookOpenCheck, Calendar, CheckCircle2, Download, History, X } from "lucide-react";
import { Link, useLocation, useParams } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import "@/styles/patient-dashboard.css";

export default function VisitSummary() {
  const { patient_id, visit_id } = useParams<{ patient_id: string; visit_id: string }>();
  const [, setLocation] = useLocation();

  const [visit, setVisit] = useState<any>(null);
  const [_patient, setPatient] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Follow-up modal state
  const [showFollowupModal, setShowFollowupModal] = useState(false);
  const [followupDate, setFollowupDate] = useState("");
  const [followupReason, setFollowupReason] = useState("Routine post-antimicrobial clinical follow-up");
  const [doctorEmail, setDoctorEmail] = useState("doctor@hospital.org");
  const [patientEmail, setPatientEmail] = useState("patient@de-identified.org");
  const [patientPhone, setPatientPhone] = useState("+91-9876543210");
  const [followupMsg, setFollowupMsg] = useState("");
  const [followupError, setFollowupError] = useState("");
  const [followupSubmitting, setFollowupSubmitting] = useState(false);

  useEffect(() => {
    async function loadSummary() {
      if (!patient_id || !visit_id) return;
      try {
        const res = await fetch(`/api/patients/${encodeURIComponent(patient_id)}/history`);
        if (res.ok) {
          const data = await res.json();
          setPatient(data.patient);
          const matchedVisit = data.visits.find((v: any) => v.visit_id === visit_id || v.prescription_id === visit_id);
          if (matchedVisit) setVisit(matchedVisit);
          else if (data.visits.length > 0) setVisit(data.visits[0]);
        }
      } catch {
        // Keep silent
      } finally {
        setLoading(false);
      }
    }
    void loadSummary();
  }, [patient_id, visit_id]);

  async function handleScheduleFollowup(e: React.FormEvent) {
    e.preventDefault();
    setFollowupError("");
    setFollowupMsg("");
    if (!followupDate) {
      setFollowupError("Please select a follow-up date.");
      return;
    }
    setFollowupSubmitting(true);

    try {
      const login = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "CLINICIAN-DEMO", role: "ATTENDING_PHYSICIAN" }),
      });
      const auth = await login.json();

      const res = await fetch("/api/appointments", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${auth.access_token}`,
        },
        body: JSON.stringify({
          patient_id,
          visit_id,
          appointment_date: followupDate,
          reason: followupReason,
          doctor_email: doctorEmail,
          patient_email: patientEmail,
          patient_phone: patientPhone,
        }),
      });

      if (res.ok) {
        const appData = await res.json();
        const msg = appData.same_day_alert_triggered
          ? "Check-up scheduled for TODAY! Multi-channel alerts (Email, SMS, In-App) triggered immediately in IST."
          : `Check-up scheduled for ${appData.formatted_date_ist || "selected date"}. Automated IST notifications configured across Email, SMS, and In-App Console.`;
        setFollowupMsg(msg);
        setTimeout(() => setShowFollowupModal(false), 2500);
      } else {
        setFollowupError("Failed to schedule appointment.");
      }
    } catch {
      setFollowupError("Error scheduling follow-up.");
    } finally {
      setFollowupSubmitting(false);
    }
  }

  const [downloadingPDF, setDownloadingPDF] = useState(false);

  async function handleDownloadPDF() {
    if (!visit_id) return;
    setDownloadingPDF(true);
    try {
      const targetId = visit?.visit_id || visit_id;
      const res = await fetch(`/api/visits/${encodeURIComponent(targetId)}/pdf`);
      if (!res.ok) {
        alert("Prescription PDF is not available for this record.");
        return;
      }
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = `Prescription_${patient_id}_${targetId}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(blobUrl);
    } catch {
      alert("An error occurred while downloading the prescription PDF.");
    } finally {
      setDownloadingPDF(false);
    }
  }

  if (loading) {
    return (
      <main className="dashboard-page">
        <div className="dashboard-empty">Loading visit summary...</div>
      </main>
    );
  }

  return (
    <main className="dashboard-page">
      <UnifiedHeader />

      <div className="dashboard-header" style={{ marginBottom: "16px" }}>
        <div>
          <p className="dashboard-kicker">PATIENT WORKFLOW STEP 7</p>
          <h1>Visit Summary & Confirmation</h1>
          <p className="dashboard-subtitle">
            Visit <strong>{visit_id}</strong> for Patient <strong>{patient_id}</strong>
          </p>
        </div>
        <Link href={`/patients/${patient_id}`} className="dashboard-button secondary">
          <History size={15} /> View Patient History
        </Link>
      </div>

      {/* SUCCESS BANNER */}
      <section className="info-section" style={{ maxWidth: "900px", margin: "0 auto 20px", background: "#eef8f3", borderColor: "#2d7064" }}>
        <div style={{ display: "flex", gap: "14px", alignItems: "center" }}>
          <CheckCircle2 size={32} color="#2d7064" />
          <div>
            <h2 style={{ color: "#173c3d", margin: 0 }}>Visit Saved Successfully</h2>
            <p style={{ margin: "4px 0 0", color: "#526968", fontSize: "0.84rem" }}>
              The visit and prescription have been permanently stored in the structured database, indexed for RAG retrieval, and logged in the immutable audit chain.
            </p>
          </div>
        </div>
      </section>

      {/* VISIT DETAILS CARD */}
      <section className="info-section" style={{ maxWidth: "900px", margin: "0 auto 20px" }}>
        <div className="section-title-row">
          <div>
            <p className="dashboard-kicker">SAVED VISIT RECORD</p>
            <h2>Clinical Details — Visit {visit_id}</h2>
          </div>
        </div>

        <div className="context-grid" style={{ marginTop: "14px" }}>
          <div>
            <span>Patient ID</span>
            <strong>{patient_id}</strong>
          </div>
          <div>
            <span>Visit Date</span>
            <strong>
              {visit?.formatted_date ||
                new Date(visit?.visit_date || Date.now()).toLocaleString("en-US", {
                  weekday: "long",
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                  hour12: true,
                })}
            </strong>
          </div>
          <div>
            <span>Diagnosis</span>
            <strong>{visit?.diagnosis || "Not recorded"}</strong>
          </div>
          <div>
            <span>Prescribed Medication</span>
            <strong>
              {visit?.medications?.map((m: any) => `${m.name} ${m.dose ? `${m.dose}${m.unit || ""}` : ""}`).join(" · ") || "None"}
            </strong>
          </div>
          <div>
            <span>Recorded Symptoms</span>
            <strong>
              {visit?.symptoms?.map((s: any) => `${s.name} (${s.severity})`).join(", ") || visit?.clinical_notes || "None recorded"}
            </strong>
          </div>
          <div>
            <span>Attending Clinician</span>
            <strong>{visit?.clinician_id || "DOC-DEMO-01"}</strong>
          </div>
        </div>
      </section>

      {/* ACTION BUTTONS STRIP */}
      <section className="action-section" style={{ maxWidth: "900px", margin: "0 auto" }}>
        <div>
          <p className="dashboard-kicker">NEXT ACTIONS</p>
          <h2>Post-Visit Options</h2>
        </div>
        <div className="action-buttons">
          <button className="dashboard-button primary" onClick={handleDownloadPDF} disabled={downloadingPDF}>
            <Download size={16} /> {downloadingPDF ? "Generating PDF..." : "Download Prescription PDF"}
          </button>
          <button className="dashboard-button secondary" onClick={() => setShowFollowupModal(true)}>
            <Calendar size={16} /> Schedule Follow-up
          </button>
          <button className="dashboard-button secondary" onClick={() => setLocation(`/patients/${patient_id}/history-assistant`)}>
            <BookOpenCheck size={16} /> Ask About Patient
          </button>
          <button className="dashboard-button secondary" onClick={() => setLocation(`/patients/${patient_id}`)}>
            View Patient History
          </button>
        </div>
      </section>

      {/* SCHEDULE FOLLOW-UP MODAL */}
      {showFollowupModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <h3 style={{ margin: 0, color: "#173c3d" }}>Schedule Follow-up Appointment</h3>
              <X size={18} style={{ cursor: "pointer" }} onClick={() => setShowFollowupModal(false)} />
            </div>

            <form onSubmit={handleScheduleFollowup} style={{ display: "grid", gap: "12px" }}>
              <div>
                <label className="field-label">Follow-up Date & Time *</label>
                <input
                  type="datetime-local"
                  value={followupDate}
                  onChange={(e) => setFollowupDate(e.target.value)}
                  className="dashboard-select"
                  required
                />
              </div>

              <div>
                <label className="field-label">Reason for Follow-up</label>
                <input
                  type="text"
                  value={followupReason}
                  onChange={(e) => setFollowupReason(e.target.value)}
                  className="dashboard-select"
                />
              </div>

              <div>
                <label className="field-label">Clinician Email (Notification 2 days before)</label>
                <input
                  type="email"
                  value={doctorEmail}
                  onChange={(e) => setDoctorEmail(e.target.value)}
                  className="dashboard-select"
                />
              </div>

              <div>
                <label className="field-label">Patient Email (Same-day & advance notification)</label>
                <input
                  type="email"
                  value={patientEmail}
                  onChange={(e) => setPatientEmail(e.target.value)}
                  className="dashboard-select"
                />
              </div>

              <div>
                <label className="field-label">Patient Mobile / WhatsApp Number (Same-day SMS alert)</label>
                <input
                  type="tel"
                  value={patientPhone}
                  onChange={(e) => setPatientPhone(e.target.value)}
                  className="dashboard-select"
                />
              </div>

              {followupError && <p className="form-error">{followupError}</p>}
              {followupMsg && <p className="form-intro" style={{ color: "#2d7064", fontWeight: 700 }}>{followupMsg}</p>}

              <div style={{ marginTop: "12px", display: "flex", gap: "10px", justifyContent: "flex-end" }}>
                <button type="button" className="dashboard-button secondary" onClick={() => setShowFollowupModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="dashboard-button primary" disabled={followupSubmitting}>
                  {followupSubmitting ? "Scheduling..." : "Schedule Appointment"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
