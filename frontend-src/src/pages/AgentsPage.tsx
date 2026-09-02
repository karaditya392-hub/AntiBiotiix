import { useEffect, useState } from "react";
import { Bot, FileStack, Search } from "lucide-react";
import ClinicalToolsLayout from "@/components/ClinicalToolsLayout";
import IngestionAgentPanel from "@/components/IngestionAgentPanel";
import SearchAgentPanel from "@/components/SearchAgentPanel";
import type { FlowGraph } from "@/components/AgentFlowGraph";
import "@/styles/patient-dashboard.css";
import "@/styles/agent-flow.css";

/**
 * The agent console — both pipelines, each drawn start node to end node.
 *
 * WHAT THIS PAGE IS FOR. The two agent pipelines make decisions a clinician has
 * to be able to audit: which documents were admitted to the corpus and at what
 * standing, and which web sources were allowed to appear beside a national
 * guideline. Those decisions were previously visible only as a JSON blob in a
 * response body. Here each one is a node you can click.
 *
 * The graph is fetched from `/api/agents/graph` rather than hardcoded here, so
 * it cannot drift from the pipeline it claims to describe.
 */

type AgentStatus = {
  agent_llm_configured: boolean;
  agent_llm_model: string | null;
  web_search_enabled: boolean;
  web_search_provider: string | null;
  web_filter_threshold: number;
  embedding_backend: string;
  retrieval_is_semantic: boolean;
  corpus_documents: number;
  corpus_chunks: number;
  parallel_fan_out: boolean;
  render_schema: string;
  ingestion_validation_requires_model: boolean;
  rule_engine_independent_of_this_layer: boolean;
};

type Tab = "search" | "ingestion";

export default function AgentsPage() {
  const [tab, setTab] = useState<Tab>("search");
  const [graphs, setGraphs] = useState<Record<string, FlowGraph>>({});
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      fetch("/api/agents/graph").then((r) => (r.ok ? r.json() : Promise.reject(r.status))),
      fetch("/api/agents/status").then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([graphData, statusData]) => {
        if (cancelled) return;
        const byId: Record<string, FlowGraph> = {};
        (graphData?.pipelines ?? []).forEach((p: FlowGraph) => {
          byId[p.id] = p;
        });
        setGraphs(byId);
        setStatus(statusData);
      })
      .catch(() => {
        if (!cancelled) setLoadError("The agent layer could not be reached.");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <ClinicalToolsLayout>
      <section className="info-section" style={{ background: "#ffffff", padding: "24px", marginBottom: "18px" }}>
        <div className="section-title-row" style={{ marginBottom: "12px" }}>
          <div>
            <p className="dashboard-kicker">AGENT PIPELINES</p>
            <h2>Agent Console</h2>
          </div>
          <Bot size={24} color="#2d7064" />
        </div>

        <p style={{ color: "#607371", fontSize: "0.86rem", margin: "0 0 16px", maxWidth: "88ch", lineHeight: 1.6 }}>
          Two pipelines, each shown as the graph the backend actually declares. Run one and every
          node reports what it did, how long it took, and — for the steps that did not run — why
          not. The refusals are the point: a document held back or a web source rejected is the
          safety behaviour working, and it has to be visible to be reviewable.
        </p>

        {/* WHAT IS ACTUALLY CONFIGURED. Stated rather than assumed, because half
            these nodes behave completely differently with no API key, and a UI
            that implies a model ran when none did is the worst version of this
            page. */}
        {status && (
          <div className="agent-status-strip">
            <span className={`agent-status-pill ${status.agent_llm_configured ? "is-on" : "is-off"}`}>
              <i />
              Agent model{" "}
              <b>{status.agent_llm_configured ? status.agent_llm_model : "not configured"}</b>
            </span>
            <span className={`agent-status-pill ${status.web_search_enabled ? "is-on" : "is-off"}`}>
              <i />
              Web path{" "}
              <b>{status.web_search_enabled ? status.web_search_provider : "off"}</b>
            </span>
            <span className={`agent-status-pill ${status.retrieval_is_semantic ? "is-on" : "is-off"}`}>
              <i />
              Retrieval{" "}
              <b>{status.retrieval_is_semantic ? "semantic" : "lexical fallback"}</b>
            </span>
            <span className="agent-status-pill is-on">
              <i />
              Vector DB{" "}
              <b>
                {status.corpus_documents.toLocaleString()} docs ·{" "}
                {status.corpus_chunks.toLocaleString()} chunks
              </b>
            </span>
            <span className={`agent-status-pill ${status.parallel_fan_out ? "is-on" : "is-off"}`}>
              <i />
              Fan-out <b>{status.parallel_fan_out ? "parallel" : "sequential"}</b>
            </span>
          </div>
        )}

        {loadError && (
          <div className="form-error" style={{ borderRadius: "4px" }}>
            {loadError}
          </div>
        )}

        <div className="agent-tabs">
          <button
            type="button"
            className={`agent-tab${tab === "search" ? " is-active" : ""}`}
            onClick={() => setTab("search")}
          >
            <Search size={19} color="#2d7064" style={{ flexShrink: 0, marginTop: "2px" }} />
            <span>
              <h4>Evidence Search Agent</h4>
              <p>
                One query, the vector DB and the web searched at once, web results filtered for
                authenticity, both coupled and grounded into one structured answer.
              </p>
            </span>
          </button>

          <button
            type="button"
            className={`agent-tab${tab === "ingestion" ? " is-active" : ""}`}
            onClick={() => setTab("ingestion")}
          >
            <FileStack size={19} color="#2d7064" style={{ flexShrink: 0, marginTop: "2px" }} />
            <span>
              <h4>Document Ingestion Agent</h4>
              <p>
                A PDF in, verified Markdown out — converted, validated against guardrails, ranked,
                chunked and embedded into the same vector DB the search agent reads.
              </p>
            </span>
          </button>
        </div>

        {status && !status.agent_llm_configured && (
          <p
            style={{
              fontSize: "0.78rem",
              color: "#8a4b1f",
              background: "#fdf3e3",
              border: "1px solid #e0c9a0",
              borderRadius: "4px",
              padding: "10px 12px",
              margin: 0,
              lineHeight: 1.55,
            }}
          >
            No agent model is configured. Both pipelines still run: the ingestion guardrails are
            deterministic and the search still retrieves and grounds. But no content review, no web
            filtration verdict and no composed answer is possible — the filter refuses every web
            result rather than admitting one nothing assessed, and the search returns the retrieved
            passages verbatim instead. Set <code>NVIDIA_API_KEY</code> in the single{" "}
            <code>.env</code> at the repository root.
          </p>
        )}
      </section>

      {tab === "search" ? (
        <SearchAgentPanel graph={graphs.SEARCH ?? null} status={status} />
      ) : (
        <IngestionAgentPanel graph={graphs.INGESTION ?? null} status={status} />
      )}
    </ClinicalToolsLayout>
  );
}
