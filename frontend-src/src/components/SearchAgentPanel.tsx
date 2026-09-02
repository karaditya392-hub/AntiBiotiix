import { useState } from "react";
import { CheckCircle2, Globe, Search, ShieldAlert, ShieldX, XCircle } from "lucide-react";
import AgentFlowGraph, { type FlowGraph, type Trace } from "@/components/AgentFlowGraph";
import "@/styles/agent-flow.css";

/**
 * The evidence search agent, run and rendered.
 *
 * EVERYTHING HERE IS DRAWN FROM `render`, the backend's structured contract.
 * This component decides layout; it decides nothing about authority. Which tier a
 * passage belongs to, which caveat it carries and whether it may be shown as
 * guidance are all settled server-side and arrive on the citation. That matters
 * because the origin label is the first thing that gets dropped when a layout is
 * tight, and a web passage rendered without it has silently acquired
 * national-guideline authority — the one failure in this layer that could change
 * a prescription.
 *
 * THE REJECTED WEB SOURCES ARE RENDERED, not hidden behind a toggle. A filter
 * whose refusals are invisible cannot be reviewed, and one nobody reviews is
 * indistinguishable from no filter at all.
 */

const EXAMPLES = [
  "What antibiotics does ICMR recommend for acute uncomplicated cystitis?",
  "What is the recommended empiric regimen for community-acquired pneumonia?",
  "What are the dose adjustments for nitrofurantoin in renal impairment?",
  "What is the WHO AWaRe classification for meropenem?",
];

// The node ids that are in flight while a request is open, in dispatch order, so
// the graph pulses through the pipeline rather than lighting up all at once.
const OPTIMISTIC_SEQUENCE = [
  ["SEARCH_QUERY", "SEARCH_GUARD"],
  ["SEARCH_FANOUT", "SEARCH_VECTOR", "SEARCH_WEB"],
  ["SEARCH_FILTER"],
  ["SEARCH_COUPLE", "SEARCH_STRUCTURE"],
];

type Citation = {
  index: number;
  source_label: string;
  document_title: string | null;
  issuing_org: string | null;
  version: string | null;
  location: string | null;
  source_url: string | null;
  passage: string;
  is_web_source: boolean;
  precedence_rank: number | null;
  tier: string;
  tier_label: string;
  authority_note: string;
  retrieval_score: number | null;
  reading_caveat: string | null;
  filter_score: number | null;
  filter_reason: string | null;
};

type RenderPayload = {
  question: string;
  answered: boolean;
  answer_mode: string;
  answer_mode_description: string;
  model: string | null;
  composition_rejected_because: string | null;
  sections: any[];
  citations: Citation[];
  evidence_groups: {
    tier: string;
    label: string;
    authority_note: string;
    precedence_rank: number | null;
    citation_indexes: number[];
  }[];
  evidence: {
    total: number;
    from_vector_db: number;
    from_web: number;
    sufficient_to_ground: boolean;
    insufficiency_reason: string | null;
  };
  sources: {
    vector_db: { ran: boolean; refused: boolean | null; reason: string | null; passages: number };
    web: {
      ran: boolean;
      skipped_reason: string | null;
      passages: number;
      filtration: {
        accepted_count: number;
        rejected_count: number;
        acceptance_threshold: number;
        model: string | null;
        degraded_no_model: boolean;
        verdicts: {
          url: string;
          site: string;
          accepted: boolean;
          score: number;
          reason: string;
          recognised_authority: boolean;
          assessed_by_model: boolean;
        }[];
      } | null;
    };
  };
  trace: Trace | null;
  disclaimer?: string;
};

export default function SearchAgentPanel({
  graph,
  status,
}: {
  graph: FlowGraph | null;
  status: { web_search_enabled: boolean } | null;
}) {
  const [question, setQuestion] = useState("");
  const [includeWeb, setIncludeWeb] = useState(true);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RenderPayload | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;

    setBusy(true);
    setError("");
    setResult(null);
    setStage(0);

    // The pipeline runs server-side in one request, so the client cannot observe
    // real node transitions. This walks the declared dispatch order at a fixed
    // pace purely so the graph reads as a flow — and it is REPLACED by the real
    // trace the moment the response lands. It never reports a node as finished;
    // only the trace does that.
    const ticker = window.setInterval(
      () => setStage((s) => Math.min(s + 1, OPTIMISTIC_SEQUENCE.length - 1)),
      1400,
    );

    try {
      const res = await fetch("/api/agents/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, k: 4, include_web: includeWeb }),
      });
      if (!res.ok) throw new Error(`The search agent returned ${res.status}.`);
      const data = await res.json();
      setResult(data.render ?? null);
    } catch (err: any) {
      setError(err?.message || "The search agent could not be reached.");
    } finally {
      window.clearInterval(ticker);
      setBusy(false);
    }
  }

  const filtration = result?.sources?.web?.filtration ?? null;
  const summary = result?.sections?.find((s) => s.kind === "SUMMARY");
  const findings = result?.sections?.find((s) => s.kind === "FINDINGS");
  const divergence = result?.sections?.find((s) => s.kind === "DIVERGENCE");
  const caveats = result?.sections?.find((s) => s.kind === "CAVEATS");
  const refusal = result?.sections?.find((s) => s.kind === "REFUSAL");

  return (
    <div style={{ display: "grid", gap: "18px" }}>
      <AgentFlowGraph
        graph={graph}
        trace={result?.trace ?? null}
        running={busy ? OPTIMISTIC_SEQUENCE[stage] : []}
        busy={busy}
      />

      {/* ---------------------------------------------------------------- ask */}
      <section className="info-section" style={{ background: "#ffffff", padding: "22px 25px" }}>
        <div className="section-title-row" style={{ marginBottom: "12px" }}>
          <div>
            <p className="dashboard-kicker">RUN THE SEARCH AGENT</p>
            <h2>Ask across the corpus and the web</h2>
          </div>
          <Search size={22} color="#2d7064" />
        </div>

        <div className="example-chips" style={{ marginBottom: "14px" }}>
          {EXAMPLES.map((q) => (
            <button key={q} type="button" className="example-chip" onClick={() => setQuestion(q)}>
              "{q}"
            </button>
          ))}
        </div>

        <form onSubmit={run} style={{ display: "grid", gap: "12px" }}>
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <input
              className="dashboard-select"
              style={{ flex: "1 1 320px" }}
              placeholder="Ask a clinical question about guidelines, dosing, or syndrome cover…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <button className="dashboard-button primary" type="submit" disabled={busy || !question.trim()}>
              <Search size={15} /> {busy ? "Running agents…" : "Run pipeline"}
            </button>
          </div>

          <label style={{ display: "flex", gap: "8px", alignItems: "center", fontSize: "0.78rem", color: "#526968" }}>
            <input
              type="checkbox"
              checked={includeWeb}
              onChange={(e) => setIncludeWeb(e.target.checked)}
              disabled={!status?.web_search_enabled}
              style={{ width: "auto" }}
            />
            <Globe size={13} />
            Include the web branch
            {!status?.web_search_enabled && " — not configured, so the corpus branch runs alone"}
          </label>
        </form>

        {error && (
          <div className="form-error" style={{ marginTop: "14px", borderRadius: "4px" }}>
            {error}
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------- answer */}
      {result && (
        <section className="info-section" style={{ background: "#ffffff", padding: "22px 25px" }}>
          <div className="section-title-row" style={{ marginBottom: "12px" }}>
            <div>
              <p className="dashboard-kicker">STRUCTURED OUTPUT</p>
              <h2>{result.answered ? "What the evidence says" : "Not answered"}</h2>
            </div>
            <span className={`flow-badge ${result.answered ? "ok" : "refused"}`}>
              {result.answer_mode}
            </span>
          </div>

          {/* WHICH MODE PRODUCED THIS. A reader must never have to infer whether
              a model was involved in the words in front of them. */}
          <p style={{ fontSize: "0.76rem", color: "#718281", margin: "0 0 14px", lineHeight: 1.55 }}>
            {result.answer_mode_description}
            {result.model && ` — ${result.model}`}
          </p>

          {result.composition_rejected_because && (
            <p className="evidence-caveat">
              <ShieldAlert size={13} style={{ verticalAlign: "-2px", marginRight: "5px" }} />
              The composed answer was discarded and the passages returned instead:{" "}
              {result.composition_rejected_because}
            </p>
          )}

          {refusal && (
            <div className="form-error" style={{ borderRadius: "4px", padding: "13px" }}>
              <strong>Refused.</strong> {refusal.text}
            </div>
          )}

          {!result.evidence.sufficient_to_ground && result.evidence.insufficiency_reason && (
            <div className="evidence-caveat" style={{ marginBottom: "14px" }}>
              <ShieldX size={13} style={{ verticalAlign: "-2px", marginRight: "5px" }} />
              {result.evidence.insufficiency_reason}
            </div>
          )}

          {summary?.text && (
            <p style={{ fontSize: "0.92rem", lineHeight: 1.68, color: "#203236", margin: "0 0 16px" }}>
              {summary.text}
            </p>
          )}

          {findings?.items?.length > 0 && (
            <>
              <p className="dashboard-kicker" style={{ marginBottom: "8px" }}>
                {findings.title?.toUpperCase()}
              </p>
              <ul style={{ margin: "0 0 16px", paddingLeft: "0", listStyle: "none", display: "grid", gap: "9px" }}>
                {findings.items.map((item: any, i: number) => (
                  <li
                    key={i}
                    style={{
                      fontSize: "0.85rem",
                      lineHeight: 1.6,
                      color: "#203236",
                      borderLeft: "3px solid #4e8a7a",
                      paddingLeft: "12px",
                    }}
                  >
                    {item.text}
                    {item.citation_indexes?.length > 0 && (
                      <span style={{ color: "#2d7064", fontWeight: 700, marginLeft: "6px", fontSize: "0.76rem" }}>
                        {item.citation_indexes.map((n: number) => `[${n}]`).join(" ")}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}

          {divergence?.items?.length > 0 && (
            <div style={{ marginBottom: "16px" }}>
              <p className="dashboard-kicker" style={{ marginBottom: "8px" }}>WHERE THE SOURCES DIFFER</p>
              <p style={{ fontSize: "0.76rem", color: "#718281", margin: "0 0 8px" }}>{divergence.note}</p>
              {divergence.items.map((d: any, i: number) => (
                <div key={i} className="evidence-caveat" style={{ marginBottom: "7px" }}>
                  <strong>{d.finding}</strong>
                  <br />
                  {d.resolution}
                </div>
              ))}
            </div>
          )}

          {caveats?.items?.length > 0 && (
            <div style={{ display: "grid", gap: "8px", marginBottom: "4px" }}>
              {caveats.items.map((c: string, i: number) => (
                <p key={i} className="evidence-caveat" style={{ margin: 0 }}>
                  <ShieldAlert size={13} style={{ verticalAlign: "-2px", marginRight: "5px" }} />
                  {c}
                </p>
              ))}
            </div>
          )}

          {result.disclaimer && (
            <p className="muted" style={{ fontSize: "0.73rem", marginTop: "14px", marginBottom: 0 }}>
              {result.disclaimer}
            </p>
          )}
        </section>
      )}

      {/* ---------------------------------------------------------- citations */}
      {result && result.citations.length > 0 && (
        <section className="info-section" style={{ background: "#ffffff", padding: "22px 25px" }}>
          <div className="section-title-row" style={{ marginBottom: "6px" }}>
            <div>
              <p className="dashboard-kicker">EVIDENCE, ORDERED BY AUTHORITY</p>
              <h2>
                {result.evidence.from_vector_db} from the vector DB · {result.evidence.from_web} from the web
              </h2>
            </div>
          </div>
          <p style={{ fontSize: "0.78rem", color: "#718281", margin: "0 0 16px", lineHeight: 1.55 }}>
            Grouped by standing, strongest first. A web passage never outranks a guideline and is
            never sufficient on its own.
          </p>

          {result.evidence_groups.map((group) => (
            <div key={group.tier} style={{ marginBottom: "18px" }}>
              <div style={{ display: "flex", gap: "9px", alignItems: "baseline", flexWrap: "wrap", marginBottom: "7px" }}>
                <strong style={{ fontSize: "0.84rem", color: "#173c3d" }}>{group.label}</strong>
                <span style={{ fontSize: "0.7rem", color: "#8a9996" }}>rank {group.precedence_rank ?? "—"}</span>
              </div>
              <p style={{ fontSize: "0.74rem", color: "#718281", margin: "0 0 10px", lineHeight: 1.5 }}>
                {group.authority_note}
              </p>

              <div style={{ display: "grid", gap: "10px" }}>
                {group.citation_indexes.map((index) => {
                  const c = result.citations.find((x) => x.index === index);
                  if (!c) return null;
                  return (
                    <article key={index} className="evidence-card" data-tier={c.tier}>
                      <div className="evidence-card-head">
                        <span className="evidence-index">[{c.index}]</span>
                        <span className="evidence-source" style={{ flex: 1 }}>{c.source_label}</span>
                        {c.retrieval_score != null && (
                          <span style={{ fontSize: "0.72rem", color: "#2d7064", fontWeight: 700 }}>
                            score {c.retrieval_score}
                          </span>
                        )}
                      </div>

                      {c.reading_caveat && <p className="evidence-caveat">{c.reading_caveat}</p>}

                      <p className="evidence-passage">"{c.passage}"</p>

                      <div className="evidence-meta">
                        {c.issuing_org && <span>Issuer: <strong>{c.issuing_org}</strong></span>}
                        {c.version && <span>Version: <strong>{c.version}</strong></span>}
                        {c.is_web_source && c.source_url ? (
                          <a href={c.source_url} target="_blank" rel="noopener noreferrer nofollow" style={{ color: "#2d7064" }}>
                            {c.source_url.slice(0, 60)}
                          </a>
                        ) : (
                          c.location && <span>Location: <strong>{c.location}</strong></span>
                        )}
                        {c.filter_score != null && (
                          <span>Filter score: <strong>{c.filter_score}</strong></span>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </div>
          ))}
        </section>
      )}

      {/* ------------------------------------------------------- the refusals */}
      {filtration && filtration.verdicts.length > 0 && (
        <section className="info-section" style={{ background: "#ffffff", padding: "22px 25px" }}>
          <div className="section-title-row" style={{ marginBottom: "6px" }}>
            <div>
              <p className="dashboard-kicker">AUTHENTICITY FILTER — EVERY VERDICT</p>
              <h2>
                {filtration.accepted_count} accepted · {filtration.rejected_count} rejected
              </h2>
            </div>
            <span className="flow-badge pending">threshold {filtration.acceptance_threshold}</span>
          </div>

          <p style={{ fontSize: "0.78rem", color: "#718281", margin: "0 0 14px", lineHeight: 1.55 }}>
            Every web result the search returned, and what the filter decided about it. The
            rejections are shown because a filter whose refusals are invisible cannot be reviewed.
            {filtration.model && ` Assessed by ${filtration.model}.`}
          </p>

          {filtration.degraded_no_model && (
            <p className="evidence-caveat">
              No assessing model was configured, so every result was refused rather than admitted
              unassessed. That is the designed behaviour, not an outage.
            </p>
          )}

          <div style={{ display: "grid", gap: "8px" }}>
            {filtration.verdicts.map((v, i) => (
              <div key={`${v.url}-${i}`} className={`verdict-row${v.accepted ? "" : " is-rejected"}`}>
                {v.accepted ? (
                  <CheckCircle2 size={15} color="#2d7064" style={{ flexShrink: 0, marginTop: "2px" }} />
                ) : (
                  <XCircle size={15} color="#a33d31" style={{ flexShrink: 0, marginTop: "2px" }} />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", gap: "8px", alignItems: "baseline", flexWrap: "wrap" }}>
                    <strong style={{ color: "#173c3d", fontSize: "0.78rem" }}>{v.site}</strong>
                    {v.recognised_authority && <span className="flow-badge ok">recognised authority</span>}
                    {!v.assessed_by_model && <span className="flow-badge skipped">not model-assessed</span>}
                  </div>
                  <p style={{ margin: "4px 0 3px", color: "#526968", lineHeight: 1.5 }}>{v.reason}</p>
                  <code>{v.url}</code>
                </div>
                <span className="verdict-score" style={{ color: v.accepted ? "#2d7064" : "#a33d31" }}>
                  {v.score.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Why a branch produced nothing — stated, not left blank. */}
      {result && !result.sources.web.ran && result.sources.web.skipped_reason && (
        <section className="info-section" style={{ background: "#ffffff", padding: "18px 25px" }}>
          <p className="dashboard-kicker" style={{ marginBottom: "6px" }}>WEB BRANCH DID NOT CONTRIBUTE</p>
          <p style={{ fontSize: "0.82rem", color: "#526968", margin: 0, lineHeight: 1.55 }}>
            {result.sources.web.skipped_reason}
          </p>
        </section>
      )}
    </div>
  );
}
