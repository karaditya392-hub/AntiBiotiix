import { History, UserPlus, ArrowRight } from "lucide-react";
import { useLocation } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import "@/styles/patient-dashboard.css";

export default function PatientTypeSelection() {
  const [, setLocation] = useLocation();

  return (
    <main className="dashboard-page">
      {/* UNIFIED SINGLE HEADER */}
      <UnifiedHeader />

      <section className="patient-type-container" style={{ marginTop: "20px" }}>
        <div className="patient-type-header">
          <p className="dashboard-kicker">CLINICIAN WORKFLOW</p>
          <h1>Start a Patient Visit</h1>
          <p>
            Choose whether you are working with an existing patient or registering a new patient.
          </p>
        </div>

        <div className="patient-type-grid">
          {/* RETURNING PATIENT CARD */}
          <div className="patient-type-card">
            <div className="patient-type-icon">
              <History size={32} />
            </div>
            <p className="dashboard-kicker">EXISTING RECORD</p>
            <h2>RETURNING PATIENT</h2>
            <p>
              Find an existing patient to view previous visits, diagnoses, symptoms, medications, and historical prescriptions.
            </p>
            <button
              className="dashboard-button primary"
              style={{ width: "100%", justifyContent: "center", padding: "14px" }}
              onClick={() => setLocation("/patients/returning")}
            >
              Continue as Returning Patient <ArrowRight size={16} />
            </button>
          </div>

          {/* NEW PATIENT CARD */}
          <div className="patient-type-card">
            <div className="patient-type-icon">
              <UserPlus size={32} />
            </div>
            <p className="dashboard-kicker">INITIAL RECORD</p>
            <h2>NEW PATIENT</h2>
            <p>
              Create a synthetic patient record, document initial clinical factors, and start their first visit.
            </p>
            <button
              className="dashboard-button secondary"
              style={{ width: "100%", justifyContent: "center", padding: "14px" }}
              onClick={() => setLocation("/patients/new")}
            >
              Register New Patient <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
