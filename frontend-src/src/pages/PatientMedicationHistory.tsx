import { useEffect, useState } from "react";
import { ArrowLeft, Pill } from "lucide-react";
import { Link, useParams } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import { patientName } from "@/lib/patient";
import "@/styles/patient-dashboard.css";

export default function PatientMedicationHistory() {
  const { patient_id } = useParams<{ patient_id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadMeds() {
      if (!patient_id) return;
      try {
        const res = await fetch(`/api/patients/${encodeURIComponent(patient_id)}/medications`);
        if (res.ok) setData(await res.json());
      } catch {
        // Keep silent
      } finally {
        setLoading(false);
      }
    }
    void loadMeds();
  }, [patient_id]);

  if (loading) {
    return (
      <main className="dashboard-page">
        <div className="dashboard-empty">Loading medication history...</div>
      </main>
    );
  }

  const medList = data?.medication_history || [];
  const displayedName = patientName(data?.display_name, patient_id);
  const idPrefix = displayedName === patient_id ? "" : `${patient_id} · `;

  return (
    <main className="dashboard-page">
      <UnifiedHeader />

      <div className="dashboard-header" style={{ marginBottom: "16px" }}>
        <div>
          <p className="dashboard-kicker">PRESCRIPTION MEMORY RECORD</p>
          <h1>Medication History — {displayedName}</h1>
          <p className="dashboard-subtitle">{idPrefix}Chronological record of all historical prescribed antimicrobials and medications.</p>
        </div>
        <Link href={`/patients/${patient_id}`} className="dashboard-button secondary">
          <ArrowLeft size={15} /> Back to Profile
        </Link>
      </div>

      <section className="info-section" style={{ maxWidth: "1100px", margin: "0 auto" }}>
        <div className="section-title-row" style={{ marginBottom: "14px" }}>
          <div>
            <p className="dashboard-kicker">HISTORICAL THERAPIES</p>
            <h2>Prescription Memory Table ({medList.length} items)</h2>
          </div>
        </div>

        {medList.length === 0 ? (
          <div className="dashboard-empty">
            <Pill size={28} />
            <h2>No medication history recorded</h2>
            <p>This patient has no recorded historical prescriptions in the database.</p>
          </div>
        ) : (
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
              {medList.map((m: any, idx: number) => (
                <tr key={idx}>
                  <td>{m.date}</td>
                  <td><strong>{m.visit_id || "N/A"}</strong></td>
                  <td>{m.diagnosis || "Not specified"}</td>
                  <td><strong>{m.medication}</strong></td>
                  <td>{m.dose || ""} {m.route || ""}</td>
                  <td>{m.frequency || "TID"}</td>
                  <td>{m.duration_days ? `${m.duration_days} days` : "5 days"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
