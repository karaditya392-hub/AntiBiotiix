/**
 * Per-drug evidence: where each medication's guidance actually came from.
 *
 * Shared by the patient analysis flow and the standalone Prescription Safety
 * Engine, because a clinician looking at COVERAGE-001 on either screen has the
 * same question -- "unassessed how, and what does anyone actually say about this
 * drug?" -- and two copies of this markup would answer it differently the first
 * time one of them was edited.
 *
 * The chain is shown, not just its result: held corpus first, external only where
 * the rules could not assess the drug or nothing held names it. Every passage
 * ends with where it was cited from.
 */
export default function DrugEvidencePanel({ findings }: { findings: any[] }) {
  if (!findings?.length) return null;

  return (
    <section className="info-section" style={{ maxWidth: "1000px", margin: "0 auto 20px" }}>
      <div className="section-title-row">
        <div>
          <p className="dashboard-kicker">EVIDENCE PER MEDICATION</p>
          <h2>Where Each Drug&rsquo;s Guidance Came From</h2>
        </div>
      </div>

      <p style={{ color: "#607371", fontSize: "0.84rem", margin: "8px 0 16px" }}>
        Every drug is checked against the held national corpus first &mdash; ICMR, NCDC, WHO, the
        antibiogram. Where the rules could not assess it, or nothing held names it, the system goes
        outside to the drug&rsquo;s regulatory label and the web. Each block states which source
        answered. Nothing here fired a rule or changed the stewardship priority.
      </p>

      {findings.map((res: any, ri: number) => {
        const national = res.source_tier === "NATIONAL_GUIDELINE";
        return (
          <div
            key={ri}
            style={{
              border: "1px solid #cbd9d4",
              borderRadius: "6px",
              marginBottom: "16px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                background: national ? "#eef6f2" : "#fdf3e3",
                padding: "10px 14px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: "8px",
                borderBottom: `2px solid ${national ? "#2d7064" : "#a65e38"}`,
              }}
            >
              <strong style={{ color: "#173c3d", fontSize: "0.92rem" }}>{res.drug}</strong>
              <span
                style={{
                  fontSize: "0.72rem",
                  fontWeight: 700,
                  color: national ? "#2d7064" : "#a65e38",
                }}
              >
                {national
                  ? "ANSWERED BY NATIONAL GUIDELINES"
                  : "RULES COULD NOT ASSESS IT → EXTERNAL SOURCE"}
              </span>
            </div>

            {/* The chain, stated rather than implied. */}
            <div
              style={{
                display: "flex",
                gap: "10px",
                alignItems: "center",
                flexWrap: "wrap",
                padding: "10px 14px",
                borderBottom: "1px solid #e2ece7",
                fontSize: "0.75rem",
                color: "#607371",
              }}
            >
              <span style={{ color: "#2d7064", fontWeight: 600 }}>1. Held corpus</span>
              <span>
                {res.national_evidence?.length
                  ? `✓ ${res.national_evidence.length} passage(s) naming ${res.drug}`
                  : "✗ nothing held names this drug"}
              </span>
              <span style={{ color: "#a8bfb8" }}>|</span>
              <span style={{ color: national ? "#a8bfb8" : "#a65e38", fontWeight: 600 }}>
                2. External
              </span>
              <span>
                {national
                  ? "not consulted"
                  : res.regulatory_label_found
                  ? `✓ ${res.regulatory_label_source}`
                  : "✗ no admissible external source found"}
              </span>
            </div>

            <div style={{ padding: "14px" }}>
              {/* What the written name was looked up as. Never silent: a wrong
                  brand mapping would otherwise show a different drug's
                  contraindications without saying so. */}
              {res.resolved_name?.notice && (
                <p
                  style={{
                    fontSize: "0.76rem",
                    color: "#8a4b1f",
                    background: "#fdf6ef",
                    border: "1px dashed #c9a97e",
                    borderRadius: "4px",
                    padding: "8px 10px",
                    margin: "0 0 12px",
                  }}
                >
                  {res.resolved_name.notice}
                </p>
              )}

              {/* What the rules could not assess, named. */}
              {res.coverage_gaps?.length > 0 && (
                <p
                  style={{
                    fontSize: "0.76rem",
                    color: "#8a4b1f",
                    background: "#fdf3e3",
                    border: "1px solid #e0c9a0",
                    borderRadius: "4px",
                    padding: "8px 10px",
                    margin: "0 0 12px",
                  }}
                >
                  <strong>Not assessed by any rule:</strong>{" "}
                  {res.coverage_gaps.map((g: string) => g.replace(/_/g, " ")).join(", ")}. This is
                  an absence of data, not a finding of safety.
                </p>
              )}

              {/* Held national passages. */}
              {res.national_evidence?.map((c: any, ci: number) => (
                <div
                  key={`n-${ci}`}
                  style={{
                    background: "#f0f6f1",
                    border: "1px solid #c8dcd2",
                    borderLeft: "3px solid #4e8a7a",
                    borderRadius: "4px",
                    padding: "12px",
                    marginBottom: "8px",
                  }}
                >
                  <div
                    style={{
                      fontSize: "0.78rem",
                      color: "#173c3d",
                      fontWeight: 600,
                      marginBottom: "4px",
                    }}
                  >
                    {String(c.issuing_org || "").split(",")[0]} &mdash; {c.section_page}
                  </div>
                  <p style={{ fontSize: "0.83rem", lineHeight: 1.5, color: "#203236", margin: 0 }}>
                    &ldquo;{String(c.verbatim_passage || "").slice(0, 380)}&rdquo;
                  </p>
                  <div style={{ fontSize: "0.7rem", color: "#607371", marginTop: "6px" }}>
                    Cited from: <strong>{c.document_title}</strong> &middot; rank{" "}
                    {c.precedence_rank} &middot; score {c.retrieval_score}
                  </div>
                </div>
              ))}

              {/* External findings. */}
              {res.findings?.map((f: any, fi: number) => (
                <div
                  key={`e-${fi}`}
                  style={{
                    background: "#fdf6ef",
                    border: "1px solid #e0c9a0",
                    borderLeft: "3px solid #a65e38",
                    borderRadius: "4px",
                    padding: "12px",
                    marginBottom: "8px",
                  }}
                >
                  <div style={{ fontSize: "0.82rem", color: "#8a4b1f", fontWeight: 600 }}>
                    {f.concern}
                  </div>
                  <div style={{ fontSize: "0.71rem", color: "#8a6a44", margin: "2px 0 6px" }}>
                    matched on this patient&rsquo;s <strong>{f.matched_on}</strong> &middot;{" "}
                    {f.section}
                  </div>
                  <p style={{ fontSize: "0.83rem", lineHeight: 1.5, color: "#203236", margin: 0 }}>
                    &ldquo;{String(f.excerpt || "").slice(0, 380)}&rdquo;
                  </p>
                  <div style={{ fontSize: "0.7rem", color: "#607371", marginTop: "6px" }}>
                    Cited from: <strong>{f.source}</strong> &middot;{" "}
                    {f.source_kind === "FDA_LABEL" ? "regulatory label" : "web source"} &middot;
                    retrieved {f.retrieved_at}
                  </div>
                </div>
              ))}

              {/* Nothing found, or the standing notice for what was. */}
              {!national &&
                (res.findings?.length ? (
                  <p style={{ fontSize: "0.71rem", color: "#8a6a44", margin: "6px 0 0" }}>
                    {res.findings[0].standing}
                  </p>
                ) : (
                  <p
                    style={{
                      fontSize: "0.79rem",
                      color: "#8a6a44",
                      fontStyle: "italic",
                      margin: 0,
                    }}
                  >
                    {res.note}
                  </p>
                ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}
