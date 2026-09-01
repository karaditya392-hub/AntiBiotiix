import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { Link, useLocation, useParams } from "wouter";
import UnifiedHeader from "@/components/UnifiedHeader";
import { patientName } from "@/lib/patient";
import "@/styles/patient-dashboard.css";

export default function ClinicalSafetyAnalysis() {
  const { patient_id, visit_id } = useParams<{ patient_id: string; visit_id: string }>();
  const [, setLocation] = useLocation();

  const [patient, setPatient] = useState<any>(null);
  const [draft, setDraft] = useState<any>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Override Modal state
  const [activeOverrideWarning, setActiveOverrideWarning] = useState<any>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideError, setOverrideError] = useState("");
  const [overrideSubmitting, setOverrideSubmitting] = useState(false);
  const [overriddenIds, setOverriddenIds] = useState<Record<string, string>>({});

  const [savingVisit, setSavingVisit] = useState(false);

  useEffect(() => {
    async function runAnalysis() {
      if (!patient_id) return;
      try {
        const pRes = await fetch(`/api/patients/${encodeURIComponent(patient_id)}/history`);
        if (pRes.ok) setPatient((await pRes.json()).patient);

        const draftStr = sessionStorage.getItem(`microbe:visit_draft:${patient_id}`);
        if (!draftStr) {
          setError("No active visit draft found. Please start a new visit.");
          setLoading(false);
          return;
        }
        const parsedDraft = JSON.parse(draftStr);
        setDraft(parsedDraft);

        // Submit prescription for rule analysis
        const prescRes = await fetch("/api/prescriptions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            patient_id,
            diagnosis: parsedDraft.diagnosis,
            raw_text: parsedDraft.raw_text,
            items: parsedDraft.prescription_items || [],
          }),
        });

        if (!prescRes.ok) throw new Error("Prescription submission failed.");
        const prescData = await prescRes.json();

        // Run 24 deterministic rules
        const analyzeRes = await fetch(`/api/prescriptions/${prescData.prescription_id}/analyze`, {
          method: "POST",
        });
        if (analyzeRes.ok) {
          setAnalysis(await analyzeRes.json());
        }
      } catch (err: any) {
        setError(err.message || "Failed to analyze prescription.");
      } finally {
        setLoading(false);
      }
    }
    void runAnalysis();
  }, [patient_id]);

  async function handleConfirmOverride(e: React.FormEvent) {
    e.preventDefault();
    setOverrideError("");
    if (!overrideReason.trim() || overrideReason.trim().length < 10) {
      setOverrideError("A substantive clinical rationale (minimum 10 characters) is required to override safety warnings.");
      return;
    }
    setOverrideSubmitting(true);

    try {
      const login = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "CLINICIAN-DEMO", role: "ATTENDING_PHYSICIAN" }),
      });
      const auth = await login.json();

      const res = await fetch(`/api/warnings/${activeOverrideWarning.warning_id}/override`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${auth.access_token}`,
        },
        body: JSON.stringify({
          warning_id: activeOverrideWarning.warning_id,
          override_reason: overrideReason.trim(),
        }),
      });

      if (res.ok) {
        setOverriddenIds({
          ...overriddenIds,
          [activeOverrideWarning.warning_id]: overrideReason.trim(),
        });
        setActiveOverrideWarning(null);
        setOverrideReason("");
      } else {
        setOverrideError("Failed to record override.");
      }
    } catch {
      setOverrideError("An error occurred during override submission.");
    } finally {
      setOverrideSubmitting(false);
    }
  }

  async function handleSaveCompletedVisit() {
    if (!patient_id || !draft) return;
    setSavingVisit(true);

    try {
      const login = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "CLINICIAN-DEMO", role: "ATTENDING_PHYSICIAN" }),
      });
      const auth = await login.json();

      const payload = {
        patient_id,
        doctor_id: "DOC-DEMO-01",
        diagnosis: draft.diagnosis,
        symptoms: draft.symptoms || [],
        symptoms_text: draft.symptoms ? draft.symptoms.map((s: any) => `${s.name} (${s.severity}, ${s.duration})`).join(", ") : undefined,
        clinical_notes: draft.clinical_notes || undefined,
        raw_prescription_text: draft.raw_text || undefined,
        prescription_items: draft.prescription_items || [],
      };

      const res = await fetch(`/api/patients/${patient_id}/visits`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${auth.access_token}`,
        },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const savedData = await res.json();
        sessionStorage.removeItem(`microbe:visit_draft:${patient_id}`);
        // Navigate to Page 7: Visit Summary
        setLocation(`/patients/${patient_id}/visits/${savedData.visit_id}/summary`);
      } else {
        setError("Failed to save visit.");
        setSavingVisit(false);
      }
    } catch {
      setError("Error saving visit.");
      setSavingVisit(false);
    }
  }

  if (loading) {
    return (
      <main className="dashboard-page">
        <div className="dashboard-empty">
          <ShieldCheck size={28} />
          <h2>Evaluating 24 Deterministic Rules...</h2>
          <p>Analyzing prescription against patient allergies, renal function, drug interactions, and antimicrobial guidelines.</p>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="dashboard-page">
        <div className="dashboard-empty">
          <ShieldAlert size={28} />
          <h2>Analysis Error</h2>
          <p>{error}</p>
          <button className="dashboard-button primary" onClick={() => setLocation(`/patients/${patient_id}/visit/new`)}>
            Return to Visit Entry
          </button>
        </div>
      </main>
    );
  }

  const warnings = analysis?.warnings || [];
  const priorityTier = analysis?.stewardship_summary?.stewardship_priority?.tier || "ROUTINE";

  return (
    <main className="dashboard-page">
      <UnifiedHeader />

      <div className="dashboard-header" style={{ marginBottom: "16px" }}>
        <div>
          <p className="dashboard-kicker">PATIENT WORKFLOW STEP 6</p>
          <h1>Clinical Decision Support Analysis</h1>
          <p className="dashboard-subtitle">
            {patientName(patient?.display_name, patient_id)} · Evaluated by 24 Deterministic Safety Rules · Priority Level: <strong>{priorityTier}</strong>
          </p>
        </div>
        <Link href={`/patients/${patient_id}/visits/${visit_id}/prescription`} className="dashboard-button secondary">
          <ArrowLeft size={15} /> Edit Prescription
        </Link>
      </div>

      {/* SUMMARY CARD */}
      <section className="info-section" style={{ maxWidth: "1000px", margin: "0 auto 20px" }}>
        <div className="section-title-row">
          <div>
            <p className="dashboard-kicker">ANALYSIS SUMMARY</p>
            <h2>Prescription & Safety Overview</h2>
          </div>
          <span className="context-badge" style={{ background: warnings.length > 0 ? "#fbe9e5" : "#e4f0e9", color: warnings.length > 0 ? "#a33d31" : "#173c3d" }}>
            {warnings.length} Safety Warning(s) Surfaced
          </span>
        </div>
        <div className="context-grid" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
          <div>
            {/* The name leads; the id follows it. This panel labelled the field
                "Patient ID" and showed only the id, which is correct as an
                identifier and tells a clinician nothing about who they are
                reviewing. */}
            <span>Patient</span>
            <strong>{patientName(patient?.display_name, patient_id)}</strong>
            <span className="muted" style={{ fontSize: "0.7rem" }}>{patient_id}</span>
          </div>
          <div>
            <span>Diagnosis</span>
            <strong>{draft?.diagnosis}</strong>
          </div>
          <div>
            <span>Prescription Items</span>
            <strong>{draft?.prescription_items?.map((i: any) => i.medication_name).join(", ") || "None"}</strong>
          </div>
          <div>
            <span>Patient Allergies</span>
            <strong>{patient?.allergies?.join(", ") || "None documented"}</strong>
          </div>
        </div>
      </section>

      {/* WARNINGS LIST */}
      <section className="info-section" style={{ maxWidth: "1000px", margin: "0 auto 20px" }}>
        <div className="section-title-row">
          <div>
            <p className="dashboard-kicker">EVALUATED SAFETY WARNINGS</p>
            <h2>Deterministic Clinical Rules Output</h2>
          </div>
        </div>

        {warnings.length === 0 ? (
          <div style={{ background: "#eef8f3", border: "1px solid #c2dbcd", padding: "16px", borderRadius: "6px", margin: "14px 0" }}>
            <strong style={{ color: "#173c3d", fontSize: "0.95rem" }}>No Safety Warnings Fired</strong>
            <p style={{ margin: "4px 0 0", color: "#526968", fontSize: "0.82rem" }}>
              The prescription passed all 24 deterministic safety rules (allergy, renal/hepatic dosing, drug interactions, antimicrobial stewardship).
            </p>
          </div>
        ) : (
          <div style={{ display: "grid", gap: "14px", marginTop: "14px" }}>
            {warnings.map((w: any) => {
              const isOverridden = Boolean(overriddenIds[w.warning_id]);
              const severityColor = w.severity === "CRITICAL" ? "#a33d31" : w.severity === "HIGH" ? "#c86d38" : "#2d7064";

              return (
                <div
                  key={w.warning_id}
                  style={{
                    background: isOverridden ? "#f0f4f2" : "#fbfcf9",
                    borderLeft: `5px solid ${isOverridden ? "#718281" : severityColor}`,
                    border: "1px solid #cbd9d4",
                    borderLeftWidth: "5px",
                    padding: "16px",
                    borderRadius: "6px",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <span style={{ background: severityColor, color: "#fff", padding: "2px 8px", borderRadius: "3px", fontSize: "0.7rem", fontWeight: 700 }}>
                        {w.severity}
                      </span>
                      <strong style={{ marginLeft: "10px", fontSize: "1rem", color: "#173c3d" }}>{w.title}</strong>
                      <span style={{ marginLeft: "10px", fontSize: "0.75rem", color: "#718281" }}>Rule: {w.rule_id}</span>
                    </div>

                    {!isOverridden ? (
                      <button
                        className="dashboard-button warning"
                        style={{ padding: "6px 12px", fontSize: "0.75rem" }}
                        onClick={() => setActiveOverrideWarning(w)}
                      >
                        Override Warning
                      </button>
                    ) : (
                      <span style={{ color: "#2d7064", fontWeight: 700, fontSize: "0.8rem" }}>
                        ✓ OVERRIDDEN
                      </span>
                    )}
                  </div>

                  <p style={{ margin: "10px 0 6px", fontSize: "0.85rem", color: "#203236" }}>
                    <b>Clinical Concern:</b> {w.clinical_concern}
                  </p>
                  <p style={{ margin: "4px 0 6px", fontSize: "0.85rem", color: "#173c3d", fontWeight: 600 }}>
                    <b>Recommendation:</b> {w.recommendation}
                  </p>

                  {w.evidence && (
                    <div style={{ marginTop: "10px", background: "#f0f6f1", padding: "10px", borderRadius: "4px", fontSize: "0.78rem" }}>
                      <b>Source Evidence:</b> {w.evidence.document_title} ({w.evidence.guideline_version})<br />
                      <i>“{w.evidence.verbatim_passage}”</i>
                    </div>
                  )}

                  {isOverridden && (
                    <div style={{ marginTop: "10px", background: "#e8efeb", padding: "8px", borderRadius: "4px", fontSize: "0.78rem" }}>
                      <b>Recorded Clinician Override Reason:</b> {overriddenIds[w.warning_id]}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* CLINICAL DECISION SUPPORT MANDATED DISCLAIMER & SAVE VISIT */}
      <section className="action-section" style={{ maxWidth: "1000px", margin: "0 auto" }}>
        <div>
          <p className="dashboard-kicker">CLINICIAN DECISION GATE</p>
          <h2>Final Prescribing Decision</h2>
          <p style={{ marginTop: "6px", fontSize: "0.82rem", color: "#526968" }}>
            "AntiBioTix does not autonomously prescribe or replace clinical judgment. Final prescribing decisions remain with the clinician."
          </p>
        </div>
        <div className="action-buttons">
          <button className="dashboard-button primary" onClick={handleSaveCompletedVisit} disabled={savingVisit} style={{ padding: "14px 24px" }}>
            {savingVisit ? "Saving Visit..." : "Save Completed Visit"} <CheckCircle2 size={16} />
          </button>
        </div>
      </section>

      {/* OVERRIDE MODAL */}
      {activeOverrideWarning && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <h3 style={{ margin: 0, color: "#173c3d" }}>Override Clinical Warning</h3>
              <X size={18} style={{ cursor: "pointer" }} onClick={() => setActiveOverrideWarning(null)} />
            </div>

            <p style={{ fontSize: "0.84rem", color: "#526968" }}>
              Rule: <strong>{activeOverrideWarning.rule_id}</strong> — {activeOverrideWarning.title}
            </p>

            <form onSubmit={handleConfirmOverride}>
              <label className="field-label">Substantive Clinical Rationale for Override *</label>
              <textarea
                rows={4}
                placeholder="Enter clinical rationale (minimum 10 characters)..."
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                className="dashboard-select"
                required
              />
              <p className="muted" style={{ fontSize: "0.72rem", marginTop: "4px" }}>
                Overriding will log your clinical justification into the immutable SHA-256 audit trail.
              </p>

              {overrideError && <p className="form-error" style={{ marginTop: "8px" }}>{overrideError}</p>}

              <div style={{ marginTop: "16px", display: "flex", gap: "10px", justifyContent: "flex-end" }}>
                <button type="button" className="dashboard-button secondary" onClick={() => setActiveOverrideWarning(null)}>
                  Cancel
                </button>
                <button type="submit" className="dashboard-button warning" disabled={overrideSubmitting}>
                  {overrideSubmitting ? "Submitting..." : "Confirm Override"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
