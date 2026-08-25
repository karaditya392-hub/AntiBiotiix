import { useEffect, useState } from "react";
import { ShieldAlert, RotateCcw, ChevronDown, ChevronUp } from "lucide-react";
import ClinicalToolsLayout from "@/components/ClinicalToolsLayout";
import "@/styles/patient-dashboard.css";

export default function ReferencePage() {
  const [stgConditions, setStgConditions] = useState<any[]>([]);
  const [stwConditions, setStwConditions] = useState<any[]>([]);
  const [amrData, setAmrData] = useState<any[]>([]);
  const [precedence, setPrecedence] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<"stg" | "stw" | "amr" | "precedence">("stg");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [detailCache, setDetailCache] = useState<Record<string, any>>({});
  const [loadingDetail, setLoadingDetail] = useState<string | null>(null);

  async function loadReferenceData() {
    setLoading(true);
    setError("");
    try {
      const [stgRes, stwRes, amrRes, precRes] = await Promise.all([
        fetch("/api/guidelines/stg-conditions"),
        fetch("/api/guidelines/stw-conditions"),
        fetch("/api/guidelines/amr-data"),
        fetch("/api/guidelines/precedence"),
      ]);

      if (!stgRes.ok) throw new Error("Clinical reference service unavailable");

      const stgData = await stgRes.json();
      const stwData = stwRes.ok ? await stwRes.json() : {};
      const amrDataRaw = amrRes.ok ? await amrRes.json() : {};
      const precDataRaw = precRes.ok ? await precRes.json() : {};

      setStgConditions(Array.isArray(stgData) ? stgData : (stgData.conditions || []));
      setStwConditions(Array.isArray(stwData) ? stwData : (stwData.conditions || []));
      setAmrData(Array.isArray(amrDataRaw) ? amrDataRaw : (amrDataRaw.records || []));
      setPrecedence(Array.isArray(precDataRaw) ? precDataRaw : (precDataRaw.hierarchy || []));
    } catch (err: any) {
      setError(err.message || "Failed to load clinical reference corpus.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadReferenceData();
  }, []);

  async function toggleExpand(source: "stg" | "stw", conditionKey: string) {
    const fullKey = `${source}:${conditionKey}`;
    if (expandedKey === fullKey) {
      setExpandedKey(null);
      return;
    }

    setExpandedKey(fullKey);
    if (detailCache[fullKey]) return;

    setLoadingDetail(fullKey);
    try {
      const endpoint = source === "stg" ? "/api/guidelines/stg-conditions" : "/api/guidelines/stw-conditions";
      const res = await fetch(`${endpoint}?condition=${encodeURIComponent(conditionKey)}`);
      if (res.ok) {
        const body = await res.json();
        setDetailCache((prev) => ({
          ...prev,
          [fullKey]: body.condition || {},
        }));
      }
    } catch {
      // Keep silent
    } finally {
      setLoadingDetail(null);
    }
  }

  const filteredStg = stgConditions.filter(
    (c) =>
      !query.trim() ||
      c.condition_name?.toLowerCase().includes(query.toLowerCase()) ||
      c.chapter?.toLowerCase().includes(query.toLowerCase()) ||
      c.condition_key?.toLowerCase().includes(query.toLowerCase())
  );

  const filteredStw = stwConditions.filter(
    (c) =>
      !query.trim() ||
      c.condition_name?.toLowerCase().includes(query.toLowerCase()) ||
      c.specialty?.toLowerCase().includes(query.toLowerCase()) ||
      c.infection_type?.toLowerCase().includes(query.toLowerCase()) ||
      c.icd10?.toLowerCase().includes(query.toLowerCase())
  );

  const filteredAmr = amrData.filter(
    (a) =>
      !query.trim() ||
      a.organism?.toLowerCase().includes(query.toLowerCase()) ||
      a.antimicrobial?.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <ClinicalToolsLayout>
      <section className="info-section" style={{ background: "#ffffff", padding: "24px" }}>
        <div className="section-title-row" style={{ marginBottom: "16px" }}>
          <div>
            <p className="dashboard-kicker">KNOWLEDGE BASE & GUIDELINE REFERENCE</p>
            <h2>Clinical Reference Knowledge Base</h2>
          </div>
          <button className="dashboard-button secondary" onClick={loadReferenceData}>
            <RotateCcw size={14} /> Refresh Reference
          </button>
        </div>

        {/* SUB-TABS & SEARCH BAR */}
        <div style={{ display: "flex", gap: "10px", marginBottom: "18px", flexWrap: "wrap" }}>
          <button
            className={`dashboard-button ${activeTab === "stg" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("stg")}
          >
            ICMR STG 2022-23 ({stgConditions.length})
          </button>

          <button
            className={`dashboard-button ${activeTab === "stw" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("stw")}
          >
            ICMR STW 2022 Workflows ({stwConditions.length})
          </button>

          <button
            className={`dashboard-button ${activeTab === "amr" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("amr")}
          >
            AMR Antibiograms ({amrData.length})
          </button>

          <button
            className={`dashboard-button ${activeTab === "precedence" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("precedence")}
          >
            Guideline Precedence Hierarchy
          </button>
        </div>

        <div style={{ marginBottom: "20px" }}>
          <label className="field-label">Search Reference Knowledge Base</label>
          <input
            type="text"
            placeholder="Search condition name, chapter, specialty, organism, or medication..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="dashboard-select"
          />
        </div>

        {/* CONTENT PANES */}
        {loading ? (
          <div className="dashboard-empty">Loading clinical reference data...</div>
        ) : error ? (
          <div className="dashboard-empty">
            <ShieldAlert size={28} color="#a33d31" />
            <h2>This clinical tool is currently unavailable</h2>
            <p>{error}</p>
            <button className="dashboard-button primary" onClick={loadReferenceData}>
              Retry
            </button>
          </div>
        ) : (
          <div>
            {/* TAB: ICMR STG 2022-23 */}
            {activeTab === "stg" && (
              <div style={{ display: "grid", gap: "12px" }}>
                {filteredStg.map((item: any, idx: number) => {
                  const fk = `stg:${item.condition_key}`;
                  const isExpanded = expandedKey === fk;
                  const detail = detailCache[fk];

                  return (
                    <article key={idx} style={{ background: "#fbfcf9", border: "1px solid #cbd9d4", padding: "16px", borderRadius: "6px" }}>
                      <div
                        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
                        onClick={() => toggleExpand("stg", item.condition_key)}
                      >
                        <div>
                          <h3 style={{ margin: "0 0 4px", color: "#173c3d", fontSize: "1.05rem" }}>{item.condition_name}</h3>
                          <span style={{ fontSize: "0.78rem", color: "#607371" }}>
                            {item.chapter || "Intra-abdominal / Infectious Diseases"} · <strong>ICMR STG 2022-23</strong>
                          </span>
                        </div>
                        <button className="dashboard-button secondary" style={{ padding: "6px 12px", fontSize: "0.76rem" }}>
                          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />} {isExpanded ? "Hide Details" : "View Details"}
                        </button>
                      </div>

                      {isExpanded && (
                        <div style={{ marginTop: "14px", paddingTop: "14px", borderTop: "1px solid #d8e2dd" }}>
                          {loadingDetail === fk ? (
                            <p className="muted">Loading full condition guidelines...</p>
                          ) : detail ? (
                            <div style={{ display: "grid", gap: "10px", fontSize: "0.85rem" }}>
                              {detail.verbatim_extract && (
                                <div><b>Verbatim Summary:</b> “{detail.verbatim_extract}”</div>
                              )}
                              {detail.presentation && detail.presentation.length > 0 && (
                                <div>
                                  <b>Clinical Presentation:</b>
                                  <ul style={{ margin: "4px 0", paddingLeft: "20px" }}>
                                    {detail.presentation.map((p: string, pIdx: number) => (
                                      <li key={pIdx}>{p}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {detail.organisms && detail.organisms.length > 0 && (
                                <div><b>Suspected Organisms:</b> {detail.organisms.join(", ")}</div>
                              )}
                              {detail.medications && (
                                <div style={{ background: "#f0f6f1", padding: "10px", borderRadius: "4px" }}>
                                  <b>Recommended Therapy:</b>
                                  {detail.medications.first_choice && (
                                    <div>First Choice: <strong>{detail.medications.first_choice.join(", ")}</strong></div>
                                  )}
                                  {detail.medications.alternative && (
                                    <div>Alternative: <strong>{detail.medications.alternative.join(", ")}</strong></div>
                                  )}
                                  {detail.medications.note && <i>Note: {detail.medications.note}</i>}
                                </div>
                              )}
                              {detail.comments && <div><b>Clinical Guidance Comments:</b> {detail.comments}</div>}
                            </div>
                          ) : (
                            <p className="muted">Detailed guidelines unavailable.</p>
                          )}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}

            {/* TAB: ICMR STW 2022 */}
            {activeTab === "stw" && (
              <div style={{ display: "grid", gap: "12px" }}>
                {filteredStw.map((item: any, idx: number) => {
                  const fk = `stw:${item.condition_key}`;
                  const isExpanded = expandedKey === fk;
                  const detail = detailCache[fk];

                  return (
                    <article key={idx} style={{ background: "#fbfcf9", border: "1px solid #cbd9d4", padding: "16px", borderRadius: "6px" }}>
                      <div
                        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
                        onClick={() => toggleExpand("stw", item.condition_key)}
                      >
                        <div>
                          <h3 style={{ margin: "0 0 4px", color: "#173c3d", fontSize: "1.05rem" }}>{item.condition_name}</h3>
                          <span style={{ fontSize: "0.78rem", color: "#607371" }}>
                            Specialty: {item.specialty || "General Medicine"} · ICD-10: {item.icd10 || "N/A"} · <strong>ICMR STW 2022</strong>
                          </span>
                        </div>
                        <button className="dashboard-button secondary" style={{ padding: "6px 12px", fontSize: "0.76rem" }}>
                          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />} {isExpanded ? "Hide Details" : "View Details"}
                        </button>
                      </div>

                      {isExpanded && (
                        <div style={{ marginTop: "14px", paddingTop: "14px", borderTop: "1px solid #d8e2dd" }}>
                          {loadingDetail === fk ? (
                            <p className="muted">Loading workflow details...</p>
                          ) : detail ? (
                            <div style={{ display: "grid", gap: "10px", fontSize: "0.85rem" }}>
                              {detail.infection_type && <div><b>Infection Category:</b> {detail.infection_type}</div>}
                              {detail.source_document_id && <div><b>Document Source:</b> {detail.source_document_id}</div>}
                              {detail.source_page && <div><b>Citation Page:</b> Page {detail.source_page}</div>}
                            </div>
                          ) : (
                            <p className="muted">Workflow details unavailable.</p>
                          )}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}

            {/* TAB: AMR SURVEILLANCE */}
            {activeTab === "amr" && (
              <table className="patient-table">
                <thead>
                  <tr>
                    <th>Organism</th>
                    <th>Antimicrobial Agent</th>
                    <th>Resistance Rate (%)</th>
                    <th>Susceptibility Rate (%)</th>
                    <th>Surveillance Period</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAmr.map((row: any, idx: number) => (
                    <tr key={idx}>
                      <td><strong>{row.organism}</strong></td>
                      <td>{row.antimicrobial}</td>
                      <td>
                        <span style={{ color: (row.resistance_rate ?? 0) > 30 ? "#a33d31" : "#2d7064", fontWeight: 700 }}>
                          {row.resistance_rate !== undefined ? `${row.resistance_rate}%` : "N/A"}
                        </span>
                      </td>
                      <td>{row.susceptibility_rate !== undefined ? `${row.susceptibility_rate}%` : "N/A"}</td>
                      <td>{row.surveillance_year || "2023-2024"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {/* TAB: PRECEDENCE HIERARCHY */}
            {activeTab === "precedence" && (
              <div style={{ display: "grid", gap: "12px" }}>
                {precedence.length === 0 ? (
                  <article style={{ background: "#fbfcf9", border: "1px solid #cbd9d4", padding: "16px", borderRadius: "6px" }}>
                    <h4>Guideline Precedence Order</h4>
                    <ol style={{ paddingLeft: "20px", fontSize: "0.88rem", lineHeight: "1.6" }}>
                      <li><strong>Local Hospital Antimicrobial Formulary (Rank 1)</strong> — Overrides regional/national defaults if local antibiogram indicates resistance.</li>
                      <li><strong>ICMR STG 2022-23 National Guidelines (Rank 2)</strong> — Primary national reference for clinical syndromes and first-line dosing.</li>
                      <li><strong>WHO AWaRe 2023 Classification (Rank 3)</strong> — Global stewardship framework (Access, Watch, Reserve categorization).</li>
                      <li><strong>FDA / DailyMed Approved Drug Labels (Rank 4)</strong> — Regulatory safety warnings, black-box warnings, contraindications.</li>
                    </ol>
                  </article>
                ) : (
                  precedence.map((p: any, idx: number) => (
                    <article key={idx} style={{ background: "#fbfcf9", border: "1px solid #cbd9d4", padding: "16px", borderRadius: "6px" }}>
                      <strong style={{ color: "#173c3d" }}>Rank {p.rank || idx + 1}: {p.authority_name || p.document_title}</strong>
                      <p style={{ margin: "4px 0", fontSize: "0.84rem" }}>{p.description || p.precedence_rule}</p>
                    </article>
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </ClinicalToolsLayout>
  );
}
