import { useEffect, useState } from "react";
import { ShieldCheck, Plus, X, ShieldAlert } from "lucide-react";
import ClinicalToolsLayout from "@/components/ClinicalToolsLayout";
import "@/styles/patient-dashboard.css";
import { useRuleCount } from "@/hooks/useRuleCount";
import { patientName } from "@/lib/patient";

export default function SafetyEnginePage() {
  // Read from the engine rather than restated from memory; see useRuleCount.
  const ruleCount = useRuleCount();
  const [presets, setPresets] = useState<any[]>([]);
  const [patients, setPatients] = useState<any[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState("");
  const [selectedPatient, setSelectedPatient] = useState<any>(null);

  const [diagnosis, setDiagnosis] = useState("");
  const [rawText, setRawText] = useState("");
  const [items, setItems] = useState<any[]>([]);

  const [medName, setMedName] = useState("");
  const [medDose, setMedDose] = useState("");
  const [medUnit, setMedUnit] = useState("mg");
  const [medRoute, setMedRoute] = useState("PO");
  const [medFreq, setMedFreq] = useState("TID");
  const [medDur, setMedDur] = useState("7");

  const [analysis, setAnalysis] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState("");

  // Override Modal state
  const [activeOverride, setActiveOverride] = useState<any>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideError, setOverrideError] = useState("");
  const [overrideSubmitting, setOverrideSubmitting] = useState(false);
  const [overriddenMap, setOverriddenMap] = useState<Record<string, string>>({});

  async function extractItemsForText(text: string) {
    if (!text || !text.trim()) {
      setItems([]);
      return;
    }
    setExtracting(true);
    try {
      const res = await fetch("/api/prescriptions/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_text: text.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.items && data.items.length > 0) {
          setItems(data.items);
        } else {
          setItems([]);
        }
      } else {
        setItems([]);
      }
    } catch {
      setItems([]);
    } finally {
      setExtracting(false);
    }
  }

  async function loadInitialData() {
    try {
      const [pRes, patRes] = await Promise.all([
        fetch("/api/scenario-presets"),
        fetch("/api/patients"),
      ]);
      let loadedPresets: any[] = [];
      let loadedPatients: any[] = [];

      if (pRes.ok) {
        loadedPresets = await pRes.json();
        setPresets(loadedPresets);
      }
      if (patRes.ok) {
        loadedPatients = await patRes.json();
        setPatients(loadedPatients);
      }

      if (loadedPresets.length > 0) {
        const firstPreset = loadedPresets[0];
        setSelectedPatientId(firstPreset.patient_id);
        const p = loadedPatients.find((pat) => pat.patient_id === firstPreset.patient_id);
        setSelectedPatient(p || null);
        setDiagnosis(firstPreset.diagnosis || "");
        setRawText(firstPreset.text || "");
        // Deliberately not extracted. The page opening with a medication already
        // queued for evaluation invites the clinician to analyse an order they
        // never placed.
      } else if (loadedPatients.length > 0) {
        const firstPat = loadedPatients[0];
        setSelectedPatientId(firstPat.patient_id);
        setSelectedPatient(firstPat);
        setDiagnosis("Clinical Safety Review");
        setRawText("");
        setItems([]);
      }
    } catch {
      // Keep silent
    }
  }

  useEffect(() => {
    void loadInitialData();
  }, []);

  function handleSelectPatient(pid: string) {
    setSelectedPatientId(pid);
    const p = patients.find((pat) => pat.patient_id === pid);
    setSelectedPatient(p || null);
    setAnalysis(null);
    setError("");

    // Look for a matching scenario preset for this patient
    const preset = presets.find((pr) => pr.patient_id === pid);
    if (preset) {
      setDiagnosis(preset.diagnosis || "");
      setRawText(preset.text || "");
    } else {
      setDiagnosis("Clinical Safety Review");
      setRawText("");
    }
    // Always cleared, preset or not. Items carried over from the previous patient
    // would otherwise be evaluated against this one's allergies and renal function,
    // and the result would look like a finding about a prescription nobody wrote.
    setItems([]);
  }

  function handleSelectPreset(preset: any) {
    setSelectedPatientId(preset.patient_id);
    const p = patients.find((pat) => pat.patient_id === preset.patient_id);
    setSelectedPatient(p || null);
    setDiagnosis(preset.diagnosis || "");
    setRawText(preset.text || "");
    setAnalysis(null);
    setError("");
    // The scenario loads the patient, the diagnosis and the order NOTE. It does not
    // put anything into the evaluation list: choosing a teaching scenario is not the
    // same act as ordering a medication, and a drug appearing in "Order Items for
    // Evaluation" without the clinician having entered it is exactly the kind of
    // silent addition a prescribing tool must never make. The note is parsed only
    // when "Parse & Extract Order Items" is pressed.
    setItems([]);
  }

  function addMedication() {
    if (!medName.trim()) return;
    const newItem = {
      medication_name: medName.trim(),
      dose: medDose ? Number(medDose) : undefined,
      unit: medUnit,
      route: medRoute,
      frequency: medFreq,
      duration_days: medDur ? Number(medDur) : undefined,
    };
    const updated = [...items, newItem];
    setItems(updated);

    // Format description and synchronize rawText
    const dosePart = newItem.dose ? `${newItem.dose}${newItem.unit || 'mg'}` : '';
    const durPart = newItem.duration_days ? `for ${newItem.duration_days} days` : '';
    const itemSummary = [newItem.medication_name, dosePart, newItem.route, newItem.frequency, durPart]
      .filter(Boolean)
      .join(" ");

    if (rawText.trim()) {
      setRawText(`${rawText.trim()}; ${itemSummary}`);
    } else {
      setRawText(itemSummary);
    }

    setMedName("");
    setMedDose("");
    setAnalysis(null);
  }

  function removeItem(index: number) {
    setItems(items.filter((_, i) => i !== index));
    setAnalysis(null);
  }

  async function runSafetyAnalysis() {
    if (!selectedPatientId) {
      setError("Please select a patient scenario.");
      return;
    }
    // Nothing to evaluate is not the same as nothing wrong. Submitting an empty
    // order returns a clean analysis, and a clean result on a prescription that was
    // never entered reads as an all-clear the engine did not give.
    if (items.length === 0) {
      setError(
        "No order items to evaluate. Add a medication, or parse them from the "
        + "free-text order note, before running the safety analysis."
      );
      return;
    }
    setAnalyzing(true);
    setError("");
    setAnalysis(null);

    try {
      // Create prescription order
      const prescRes = await fetch("/api/prescriptions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: selectedPatientId,
          diagnosis: diagnosis.trim(),
          raw_text: rawText.trim(),
          items: items,
        }),
      });

      if (!prescRes.ok) throw new Error("Could not submit prescription for analysis.");
      const prescData = await prescRes.json();

      // Execute 24-rule analysis
      const analyzeRes = await fetch(`/api/prescriptions/${prescData.prescription_id}/analyze`, {
        method: "POST",
      });

      if (analyzeRes.ok) {
        setAnalysis(await analyzeRes.json());
      } else {
        throw new Error("Safety analysis engine execution failed.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to run safety analysis.");
    } finally {
      setAnalyzing(false);
    }
  }

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

      const res = await fetch(`/api/warnings/${activeOverride.warning_id}/override`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${auth.access_token}`,
        },
        body: JSON.stringify({
          warning_id: activeOverride.warning_id,
          override_reason: overrideReason.trim(),
        }),
      });

      if (res.ok) {
        setOverriddenMap({
          ...overriddenMap,
          [activeOverride.warning_id]: overrideReason.trim(),
        });
        setActiveOverride(null);
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

  const warnings = analysis?.warnings || [];

  return (
    <ClinicalToolsLayout>
      <section className="info-section" style={{ background: "#ffffff", padding: "24px" }}>
        <div className="section-title-row" style={{ marginBottom: "14px" }}>
          <div>
            <p className="dashboard-kicker">24 DETERMINISTIC CLINICAL RULES</p>
            <h2>Prescription Safety Engine</h2>
          </div>
          <ShieldCheck size={24} color="#a65e38" />
        </div>

        <p style={{ color: "#607371", fontSize: "0.86rem", margin: "0 0 16px" }}>
          Run real-time rule evaluation across allergy cross-reactivity, renal/hepatic dosing limits, drug-drug interactions, and antimicrobial stewardship guidelines.
        </p>

        {/* PRESETS & PATIENT SELECTION */}
        <div style={{ background: "#f0f6f1", border: "1px solid #c8dcd2", padding: "16px", borderRadius: "6px", marginBottom: "20px" }}>
          <label className="field-label" style={{ marginTop: 0 }}>Select Patient Scenario for Safety Review</label>
          <select
            className="dashboard-select"
            value={selectedPatientId}
            onChange={(e) => handleSelectPatient(e.target.value)}
          >
            {/* Name first, then the record key. Picking a patient from a list of
                twenty ids means matching "PATIENT-014" against nothing a clinician
                holds in their head. */}
            {patients.map((p) => (
              <option key={p.patient_id} value={p.patient_id}>
                {patientName(p.display_name, p.patient_id)} · {p.patient_id} · {p.age} yrs · {p.sex} · Allergies: {p.allergies?.join(", ") || "None"}
              </option>
            ))}
          </select>

          {presets.length > 0 && (
            <div style={{ marginTop: "12px" }}>
              <span className="field-label" style={{ fontSize: "0.72rem" }}>Quick Teaching Scenario Chips:</span>
              <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "6px" }}>
                {presets.slice(0, 8).map((pr) => (
                  <button
                    key={pr.key}
                    type="button"
                    className="example-chip"
                    onClick={() => handleSelectPreset(pr)}
                  >
                    {patientName(
                      patients.find((p) => p.patient_id === pr.patient_id)?.display_name,
                      pr.patient_id,
                    )}: {pr.diagnosis}
                  </button>
                ))}
              </div>
            </div>
          )}

          {selectedPatient && (
            <div style={{ marginTop: "12px", background: "#ffffff", padding: "12px", borderRadius: "4px", fontSize: "0.8rem" }}>
              <b>Selected Profile:</b>{" "}
              <strong>{patientName(selectedPatient.display_name, selectedPatient.patient_id)}</strong>{" "}
              <span className="muted">{selectedPatient.patient_id}</span> ({selectedPatient.age} yrs, {selectedPatient.sex}) · eGFR: {selectedPatient.egfr_ml_min ?? "Not assessed"} mL/min · Allergies: <strong>{selectedPatient.allergies?.join(", ") || "None documented"}</strong> · Active Meds: {selectedPatient.active_medications?.join(", ") || "None"}
            </div>
          )}
        </div>

        {/* PRESCRIPTION ORDER FORM */}
        <div style={{ display: "grid", gap: "14px", marginBottom: "20px" }}>
          <div>
            <label className="field-label">Diagnosis / Indication</label>
            <input
              type="text"
              value={diagnosis}
              onChange={(e) => setDiagnosis(e.target.value)}
              className="dashboard-select"
            />
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label className="field-label">Free-Text Order Note</label>
              {rawText && (
                <button
                  type="button"
                  style={{ fontSize: "0.75rem", background: "transparent", border: "none", color: "#0f7774", cursor: "pointer", fontWeight: 600 }}
                  onClick={() => extractItemsForText(rawText)}
                >
                  {extracting ? "Extracting..." : "⚡ Parse & Extract Order Items"}
                </button>
              )}
            </div>
            <input
              type="text"
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              /* No onBlur extraction. Tabbing out of a text field is not a decision
                 to order a drug, and it put items into the evaluation list without
                 the clinician asking. The button above is the explicit way to parse
                 this note. */
              className="dashboard-select"
            />
          </div>

          <div>
            <label className="field-label">Add Structured Medication Order</label>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <input placeholder="Drug name" value={medName} onChange={(e) => setMedName(e.target.value)} style={{ flex: 2 }} className="dashboard-select" />
              <input placeholder="Dose" type="number" value={medDose} onChange={(e) => setMedDose(e.target.value)} style={{ width: "80px" }} className="dashboard-select" />
              <select value={medUnit} onChange={(e) => setMedUnit(e.target.value)} style={{ width: "70px" }} className="dashboard-select">
                <option value="mg">mg</option>
                <option value="g">g</option>
                <option value="mcg">mcg</option>
              </select>
              <select value={medRoute} onChange={(e) => setMedRoute(e.target.value)} style={{ width: "70px" }} className="dashboard-select">
                <option value="PO">PO</option>
                <option value="IV">IV</option>                <option value="IM">IM</option>
              </select>
              <select value={medFreq} onChange={(e) => setMedFreq(e.target.value)} style={{ width: "80px" }} className="dashboard-select">
                <option value="QD">QD</option>
                <option value="BID">BID</option>
                <option value="TID">TID</option>
                <option value="QID">QID</option>
              </select>
              <input placeholder="Days" type="number" value={medDur} onChange={(e) => setMedDur(e.target.value)} style={{ width: "70px" }} className="dashboard-select" />
              <button type="button" className="dashboard-button secondary" onClick={addMedication}>
                <Plus size={15} /> Add
              </button>
            </div>
          </div>

          {/* An empty list is a state worth naming. The evaluation list used to be
              populated for the clinician, so it was never empty and never needed to
              explain itself; now that nothing is added without an explicit action,
              silence here would read as a broken page. */}
          {items.length === 0 && (
            <p className="muted" style={{ fontSize: "0.8rem", margin: "4px 0" }}>
              No order items yet. Add a medication above, or press
              {" "}<b>Parse &amp; Extract Order Items</b>{" "}
              to read them from the free-text order note.
            </p>
          )}

          {items.length > 0 && (
            <div>
              <strong>Order Items for Evaluation:</strong>
              <ul style={{ margin: "4px 0", paddingLeft: "20px" }}>
                {items.map((it, idx) => (
                  <li key={idx}>
                    {it.medication_name} {it.dose} {it.unit} {it.route} {it.frequency} for {it.duration_days} days{" "}
                    <X size={12} style={{ cursor: "pointer", color: "#a33d31" }} onClick={() => removeItem(idx)} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <button className="dashboard-button warning" onClick={runSafetyAnalysis} disabled={analyzing} style={{ padding: "12px 24px" }}>
              <ShieldCheck size={16} /> {analyzing ? `Evaluating ${ruleCount ?? ""} Rules...`.replace("  ", " ") : "Analyze Prescription Safety"}
            </button>
          </div>
        </div>

        {error && (
          <div className="dashboard-empty" style={{ margin: "16px 0" }}>
            <ShieldAlert size={28} color="#a33d31" />
            <h2>This clinical tool is currently unavailable</h2>
            <p>{error}</p>
            <button className="dashboard-button primary" onClick={runSafetyAnalysis}>
              Retry
            </button>
          </div>
        )}

        {/* ANALYSIS RESULTS DISPLAY */}
        {analysis && (
          <div style={{ marginTop: "24px", borderTop: "2px solid #d8e2dd", paddingTop: "18px" }}>
            <div className="section-title-row" style={{ marginBottom: "12px" }}>
              <div>
                <p className="dashboard-kicker">SAFETY ENGINE RESULTS</p>
                <h3>Surfaced Warnings ({warnings.length}) · Priority: {analysis.stewardship_summary?.stewardship_priority?.tier || "ROUTINE"}</h3>
              </div>
            </div>

            {warnings.length === 0 ? (
              <div style={{ background: "#eef8f3", border: "1px solid #c2dbcd", padding: "16px", borderRadius: "6px" }}>
                <strong style={{ color: "#173c3d" }}>✓ No Safety Warnings Fired</strong>
                <p style={{ margin: "4px 0 0", color: "#526968", fontSize: "0.82rem" }}>
                  The prescription passed all 24 deterministic checks (allergy, renal/hepatic dosing, drug interactions, stewardship).
                </p>
              </div>
            ) : (
              <div style={{ display: "grid", gap: "12px" }}>
                {warnings.map((w: any) => {
                  const isOverridden = Boolean(overriddenMap[w.warning_id]);
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
                          <span style={{ marginLeft: "10px", fontSize: "0.74rem", color: "#718281" }}>Rule: {w.rule_id}</span>
                        </div>

                        {!isOverridden ? (
                          <button
                            className="dashboard-button warning"
                            style={{ padding: "6px 12px", fontSize: "0.75rem" }}
                            onClick={() => setActiveOverride(w)}
                          >
                            Override Warning
                          </button>
                        ) : (
                          <span style={{ color: "#2d7064", fontWeight: 700, fontSize: "0.8rem" }}>
                            ✓ OVERRIDDEN
                          </span>
                        )}
                      </div>

                      <p style={{ margin: "8px 0 4px", fontSize: "0.85rem", color: "#203236" }}>
                        <b>Clinical Concern:</b> {w.clinical_concern}
                      </p>
                      <p style={{ margin: "4px 0", fontSize: "0.85rem", color: "#173c3d", fontWeight: 600 }}>
                        <b>Recommendation:</b> {w.recommendation}
                      </p>

                      {w.evidence && (
                        <div style={{ marginTop: "10px", background: "#f0f6f1", padding: "10px", borderRadius: "4px", fontSize: "0.78rem" }}>
                          <b>Evidence Source:</b> {w.evidence.document_title} ({w.evidence.guideline_version})<br />
                          <i>“{w.evidence.verbatim_passage}”</i>
                        </div>
                      )}

                      {isOverridden && (
                        <div style={{ marginTop: "8px", background: "#e8efeb", padding: "8px", borderRadius: "4px", fontSize: "0.78rem" }}>
                          <b>Clinician Override Rationale:</b> {overriddenMap[w.warning_id]}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>

      {/* OVERRIDE MODAL */}
      {activeOverride && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <h3 style={{ margin: 0, color: "#173c3d" }}>Override Warning ({activeOverride.rule_id})</h3>
              <X size={18} style={{ cursor: "pointer" }} onClick={() => setActiveOverride(null)} />
            </div>

            <form onSubmit={handleConfirmOverride}>
              <label className="field-label">Substantive Clinical Rationale for Override *</label>
              <textarea
                rows={3}
                placeholder="Enter clinical rationale (minimum 10 characters)..."
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                className="dashboard-select"
                required
              />

              {overrideError && <p className="form-error" style={{ marginTop: "8px" }}>{overrideError}</p>}

              <div style={{ marginTop: "14px", display: "flex", gap: "10px", justifyContent: "flex-end" }}>
                <button type="button" className="dashboard-button secondary" onClick={() => setActiveOverride(null)}>
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
    </ClinicalToolsLayout>
  );
}
