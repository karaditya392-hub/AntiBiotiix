import { History, UserPlus, ArrowRight, Lock } from "lucide-react";
import { useLocation } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import { useAuth } from "@/context/AuthContext";
import "@/styles/patient-dashboard.css";

export default function PatientTypeSelection() {
  const [, setLocation] = useLocation();
  const { isAuthenticated } = useAuth();

  const handleNavigate = (targetPath: string) => {
    if (!isAuthenticated) {
      setLocation(`/login?redirect=${encodeURIComponent(targetPath)}`);
    } else {
      setLocation(targetPath);
    }
  };

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
          {!isAuthenticated && (
            <div
              style={{
                marginTop: "12px",
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                background: "#fdf8ec",
                border: "1px solid #e2bd72",
                color: "#845e14",
                padding: "6px 14px",
                borderRadius: "6px",
                fontSize: "0.82rem",
                fontWeight: 600,
              }}
            >
              <Lock size={15} />
              <span>Authentication required: You will be prompted to log in before viewing patient records.</span>
            </div>
          )}
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
              onClick={() => handleNavigate("/patients/returning")}
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
              onClick={() => handleNavigate("/patients/new")}
            >
              Register New Patient <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
