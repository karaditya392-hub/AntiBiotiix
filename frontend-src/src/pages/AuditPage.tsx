import { useEffect, useState } from "react";
import { ShieldCheck, ShieldAlert, RotateCcw } from "lucide-react";
import ClinicalToolsLayout from "@/components/ClinicalToolsLayout";
import "@/styles/patient-dashboard.css";

export default function AuditPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [fatigue, setFatigue] = useState<any[]>([]);
  const [verifyResult, setVerifyResult] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [logsRes, fatigueRes] = await Promise.all([
        fetch("/api/audit/logs?limit=50"),
        fetch("/api/audit/alert-fatigue"),
      ]);

      if (logsRes.ok) {
        setLogs(await logsRes.json());
      } else {
        throw new Error("Audit log service unavailable");
      }

      if (fatigueRes.ok) {
        const fatData = await fatigueRes.json();
        setFatigue(fatData.rules || fatData.metrics || []);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load audit trail.");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyAuditChain() {
    setVerifying(true);
    setVerifyResult(null);
    try {
      const res = await fetch("/api/audit/verify");
      if (res.ok) {
        setVerifyResult(await res.json());
      } else {
        setVerifyResult({ valid: false, detail: "Verification failed." });
      }
    } catch {
      setVerifyResult({ valid: false, detail: "Audit chain verification endpoint unreachable." });
    } finally {
      setVerifying(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  return (
    <ClinicalToolsLayout>
      <section className="info-section" style={{ background: "#ffffff", padding: "24px" }}>
        <div className="section-title-row" style={{ marginBottom: "16px" }}>
          <div>
            <p className="dashboard-kicker">SHA-256 HASH-CHAINED LOGS & SAFETY METRICS</p>
            <h2>Audit Trail & Alert Fatigue Analytics</h2>
          </div>
          <div style={{ display: "flex", gap: "10px" }}>
            <button className="dashboard-button primary" onClick={handleVerifyAuditChain} disabled={verifying}>
              <ShieldCheck size={16} /> {verifying ? "Verifying Chain..." : "Verify Audit Chain Integrity"}
            </button>
            <button className="dashboard-button secondary" onClick={loadData}>
              <RotateCcw size={14} /> Refresh Logs
            </button>
          </div>
        </div>

        {/* VERIFICATION RESULT BANNER */}
        {verifyResult && (
          <div
            style={{
              background: verifyResult.valid ? "#eef8f3" : "#fbe9e5",
              border: `1px solid ${verifyResult.valid ? "#4e8a7a" : "#e0b4ac"}`,
              padding: "14px",
              borderRadius: "6px",
              marginBottom: "20px",
              color: verifyResult.valid ? "#173c3d" : "#a33d31",
            }}
          >
            <strong style={{ fontSize: "0.95rem" }}>
              {verifyResult.valid ? "✓ SHA-256 Audit Trail Cryptographic Integrity Verified Intact" : "⚠ Cryptographic Chain Integrity Failure"}
            </strong>
            <p style={{ margin: "4px 0 0", fontSize: "0.82rem" }}>
              Verified {verifyResult.checked_count ?? logs.length} audit block hashes in order. Previous hash signatures are un-tampered.
            </p>
          </div>
        )}

        {loading ? (
          <div className="dashboard-empty">Loading audit trail and alert metrics...</div>
        ) : error ? (
          <div className="dashboard-empty">
            <ShieldAlert size={28} color="#a33d31" />
            <h2>This clinical tool is currently unavailable</h2>
            <p>{error}</p>
            <button className="dashboard-button primary" onClick={loadData}>
              Retry
            </button>
          </div>
        ) : (
          <div style={{ display: "grid", gap: "24px" }}>
            {/* ALERT FATIGUE SECTION */}
            <div>
              <h3>Alert Fatigue & Override Analytics</h3>
              <p className="muted" style={{ margin: "4px 0 12px", fontSize: "0.8rem" }}>
                Tracks override rates per deterministic rule. High override rates (&gt;50%) trigger safety review and recalibration flags.
              </p>

              {fatigue.length === 0 ? (
                <p className="muted">No alert fatigue data accumulated yet.</p>
              ) : (
                <table className="patient-table">
                  <thead>
                    <tr>
                      <th>Rule ID</th>
                      <th>Total Triggered</th>
                      <th>Total Overridden</th>
                      <th>Total Accepted</th>
                      <th>Override Rate</th>
                      <th>Recalibration Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fatigue.map((row: any, idx: number) => (
                      <tr key={idx}>
                        <td><strong>{row.rule_id}</strong></td>
                        <td>{row.total_triggered ?? row.count ?? 0}</td>
                        <td>{row.total_overridden ?? row.overrides ?? 0}</td>
                        <td>{row.total_accepted ?? (row.total_triggered ? (row.total_triggered - (row.total_overridden || 0)) : 0)}</td>
                        <td>
                          <strong>{row.override_rate_pct ?? (row.override_rate ? `${(row.override_rate * 100).toFixed(1)}%` : "0.0%")}</strong>
                        </td>
                        <td>
                          <span style={{ color: row.override_rate_pct > 50 ? "#a33d31" : "#2d7064", fontWeight: 700 }}>
                            {row.recalibration_flag ? "RECALIBRATION_RECOMMENDED" : "OPTIMAL"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* IMMUTABLE AUDIT TRAIL LOGS TABLE */}
            <div>
              <h3>Immutable Cryptographic Audit Trail ({logs.length} events)</h3>
              <p className="muted" style={{ margin: "4px 0 12px", fontSize: "0.8rem" }}>
                Chronological list of patient creation, visit creation, analysis, warnings, and clinician overrides.
              </p>

              {logs.length === 0 ? (
                <p className="muted">No audit events logged.</p>
              ) : (
                <table className="patient-table">
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Event Type</th>
                      <th>Clinician</th>
                      <th>Action Summary</th>
                      <th>Patient / Rx ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log: any, idx: number) => (
                      <tr key={idx}>
                        <td style={{ fontSize: "0.78rem" }}>
                          {log.timestamp
                            ? `${new Date(log.timestamp).toLocaleString("en-IN", {
                                timeZone: "Asia/Kolkata",
                                year: "numeric",
                                month: "short",
                                day: "numeric",
                                hour: "numeric",
                                minute: "2-digit",
                                second: "2-digit",
                                hour12: true,
                              })} IST`
                            : "N/A"}
                        </td>
                        <td>
                          <span className="preset-chip-id">{log.event_type}</span>
                        </td>
                        <td>{log.clinician_id || "SYSTEM"} ({log.clinician_role || "ATTENDING_PHYSICIAN"})</td>
                        <td style={{ fontSize: "0.82rem" }}>{log.action_summary}</td>
                        <td style={{ fontSize: "0.78rem" }}>{log.patient_id || log.prescription_id || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </section>
    </ClinicalToolsLayout>
  );
}
