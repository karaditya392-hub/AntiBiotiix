import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, UserRound } from "lucide-react";
import { Link, useLocation } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import "@/styles/patient-dashboard.css";

type Patient = {
  patient_id: string;
  display_name?: string;
  age?: number;
  sex?: string;
  allergies?: string[];
  last_visit?: string;
  last_diagnosis?: string;
};

export default function SelectReturningPatient() {
  const [, setLocation] = useLocation();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  async function fetchPatients() {
    try {
      const url = search.trim() ? `/api/patients?q=${encodeURIComponent(search.trim())}` : "/api/patients";
      const res = await fetch(url);
      if (res.ok) {
        setPatients(await res.json());
      }
    } catch {
      // Keep state
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchPatients();
  }, [search]);

  return (
    <main className="dashboard-page">
      <UnifiedHeader />

      <div className="dashboard-header" style={{ marginBottom: "16px" }}>
        <div>
          <p className="dashboard-kicker">PATIENT WORKFLOW STEP 2A</p>
          <h1>Select Returning Patient</h1>
          <p className="dashboard-subtitle">Search for an existing patient to continue their care.</p>
        </div>
        <Link href="/" className="dashboard-button secondary">
          <ArrowLeft size={15} /> Back to Selection
        </Link>
      </div>

      <section className="info-section" style={{ maxWidth: "1100px", margin: "0 auto" }}>
        <div style={{ marginBottom: "20px" }}>
          <label className="field-label">Search Patient ID or Name</label>
          <div style={{ display: "flex", gap: "10px" }}>
            <input
              type="text"
              placeholder="Search by patient ID (e.g. PATIENT-001) or diagnosis..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="dashboard-select"
            />
          </div>
        </div>

        {loading ? (
          <div className="dashboard-empty">Loading patient records...</div>
        ) : patients.length === 0 ? (
          <div className="dashboard-empty">
            <UserRound size={28} />
            <h2>No patient found</h2>
            <p>No matching patient records were found in the system database.</p>
            <Link href="/patients/new" className="dashboard-button primary" style={{ marginTop: "12px" }}>
              Register New Patient
            </Link>
          </div>
        ) : (
          <div style={{ display: "grid", gap: "12px" }}>
            {patients.map((p) => (
              <div
                key={p.patient_id}
                style={{
                  background: "#ffffff",
                  border: "1px solid #cbd9d4",
                  borderRadius: "6px",
                  padding: "16px 20px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div>
                  <h3 style={{ margin: "0 0 4px", color: "#173c3d", fontSize: "1.1rem" }}>
                    {p.patient_id} <span style={{ fontWeight: 400, color: "#607371", fontSize: "0.9rem" }}>({p.display_name || `Patient ${p.patient_id}`})</span>
                  </h3>
                  <p style={{ margin: "2px 0", fontSize: "0.82rem", color: "#405453" }}>
                    <strong>{p.age ?? "Unknown"} years</strong> · {p.sex || "Sex not specified"} · Allergies: {p.allergies?.join(", ") || "None documented"}
                  </p>
                  <p style={{ margin: "4px 0 0", fontSize: "0.8rem", color: "#718281" }}>
                    Last Visit: <strong>{p.last_visit || "No visits recorded"}</strong> · Last Diagnosis: <strong>{p.last_diagnosis || "None"}</strong>
                  </p>
                </div>

                <button
                  className="dashboard-button primary"
                  onClick={() => setLocation(`/patients/${p.patient_id}`)}
                >
                  Select Patient <ArrowRight size={15} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
