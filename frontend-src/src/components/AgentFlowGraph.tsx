import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import "@/styles/agent-flow.css";

/**
 * The pipeline flow diagram.
 *
 * THE NODES AND EDGES COME FROM THE BACKEND (`/api/agents/graph`), not from this
 * file. A diagram maintained in the frontend is a drawing of what someone
 * believed the pipeline did on the day they drew it: it keeps showing a step
 * after that step is removed, and it shows a filtration node running when no key
 * is configured and nothing filtered anything. A reader trusts a picture more
 * than prose, so a stale picture misleads harder than no picture at all.
 *
 * Each run returns a trace keyed by the same node ids, and this component
 * colours the declared graph with the actual run. The state that matters most is
 * SKIPPED — a flow chart normally cannot say "this step did not happen, and here
 * is why", and "the web path was off" and "the web path found nothing" look
 * identical on screen without it.
 *
 * Edges are drawn in SVG from MEASURED node positions rather than computed from
 * the grid, so they stay attached when the cards wrap, the fonts load late, or
 * the container is resized.
 */

export type FlowNode = {
  id: string;
  label: string;
  kind: string;
  lane: number;
  row: number;
  description: string;
};

export type FlowEdge = { from: string; to: string; parallel?: boolean };

export type FlowGraph = {
  id: string;
  title: string;
  subtitle: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
};

export type NodeRun = {
  node_id: string;
  status: string;
  detail: string;
  duration_ms: number | null;
  metrics?: Record<string, any>;
};

export type Trace = {
  pipeline: string;
  total_ms: number;
  nodes: NodeRun[];
};

const KIND_LABEL: Record<string, string> = {
  START: "input",
  AGENT: "agent",
  DETERMINISTIC: "deterministic",
  LLM: "llm",
  STORE: "vector db",
  EXTERNAL: "external",
  GUARD: "guardrail",
  END: "output",
};

const STATUS_WORD: Record<string, string> = {
  PENDING: "not run",
  RUNNING: "running",
  OK: "done",
  SKIPPED: "skipped",
  REFUSED: "refused",
  FAILED: "failed",
  DEGRADED: "degraded",
};

function formatMs(ms: number | null | undefined): string {
  if (ms == null) return "";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Metric values are rendered, not stringified blindly — an object dumped as
 *  "[object Object]" is worse than omitting it. */
function metricPairs(metrics?: Record<string, any>): [string, string][] {
  if (!metrics) return [];
  const out: [string, string][] = [];
  for (const [key, value] of Object.entries(metrics)) {
    if (value == null || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length === 0) continue;
      if (typeof value[0] === "object") {
        out.push([key, `${value.length}`]);
        continue;
      }
      out.push([key, value.join(", ").slice(0, 90)]);
      continue;
    }
    if (typeof value === "object") continue;
    if (typeof value === "number") {
      out.push([key, Number.isInteger(value) ? `${value}` : value.toFixed(3)]);
      continue;
    }
    out.push([key, String(value).slice(0, 90)]);
  }
  return out.slice(0, 10);
}

type Props = {
  graph: FlowGraph | null;
  trace?: Trace | null;
  /** Node ids currently mid-flight, for the pulse while a request is open. */
  running?: string[];
  busy?: boolean;
};

export default function AgentFlowGraph({ graph, trace, running = [], busy = false }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [paths, setPaths] = useState<{ d: string; key: string; cls: string }[]>([]);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const nodeRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const runById = useMemo(() => {
    const map: Record<string, NodeRun> = {};
    (trace?.nodes ?? []).forEach((n) => {
      map[n.node_id] = n;
    });
    return map;
  }, [trace]);

  const statusOf = useCallback(
    (nodeId: string): string => {
      if (running.includes(nodeId)) return "RUNNING";
      return runById[nodeId]?.status ?? "PENDING";
    },
    [runById, running],
  );

  const lanes = graph ? Math.max(...graph.nodes.map((n) => n.lane)) + 1 : 0;
  const rows = graph ? Math.max(...graph.nodes.map((n) => n.row)) + 1 : 0;

  /**
   * Measure the rendered node boxes and lay the edges out between them.
   *
   * useLayoutEffect so the paths are in place before paint — computed in a plain
   * effect, the edges visibly snap into position on first render. A ResizeObserver
   * keeps them attached when the container changes or a web font arrives late and
   * reflows every card.
   */
  useLayoutEffect(() => {
    if (!graph) return;

    function measure() {
      const canvas = canvasRef.current;
      if (!canvas || !graph) return;
      const origin = canvas.getBoundingClientRect();
      const next: { d: string; key: string; cls: string }[] = [];

      for (const edge of graph.edges) {
        const a = nodeRefs.current[edge.from];
        const b = nodeRefs.current[edge.to];
        if (!a || !b) continue;
        const from = a.getBoundingClientRect();
        const to = b.getBoundingClientRect();

        const x1 = from.right - origin.left;
        const y1 = from.top + from.height / 2 - origin.top;
        const x2 = to.left - origin.left;
        const y2 = to.top + to.height / 2 - origin.top;
        // A horizontal-tangent cubic: the curve leaves and enters each card
        // side-on, so an edge that changes row still meets the box squarely.
        const bend = Math.max(18, (x2 - x1) / 2);
        const d = `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;

        const fromStatus = statusOf(edge.from);
        const toStatus = statusOf(edge.to);
        const dead = toStatus === "SKIPPED" || toStatus === "PENDING";
        const live =
          !dead &&
          ["OK", "DEGRADED", "REFUSED", "RUNNING"].includes(fromStatus) &&
          ["OK", "DEGRADED", "REFUSED", "RUNNING", "FAILED"].includes(toStatus);

        next.push({
          key: `${edge.from}->${edge.to}`,
          d,
          cls: `flow-edge${edge.parallel ? " is-parallel" : ""}${
            live ? " is-live" : dead ? " is-dead" : ""
          }`,
        });
      }
      setPaths(next);
    }

    measure();
    const observer = new ResizeObserver(measure);
    if (canvasRef.current) observer.observe(canvasRef.current);
    window.addEventListener("resize", measure);
    // Fonts land after first paint and change every card's height.
    (document as any).fonts?.ready?.then(measure).catch(() => {});
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [graph, statusOf, trace, running]);

  if (!graph) {
    return (
      <div className="flow-shell">
        <div className="flow-scroll">
          <p className="muted" style={{ margin: 0 }}>
            Loading the pipeline definition from the server…
          </p>
        </div>
      </div>
    );
  }

  const detailNode =
    graph.nodes.find((n) => n.id === selected) ??
    // Nothing picked: show the node that most recently did something, so the
    // strip is never empty and never arbitrary.
    graph.nodes.find((n) => n.id === trace?.nodes?.[trace.nodes.length - 1]?.node_id) ??
    graph.nodes[0];
  const detailRun = detailNode ? runById[detailNode.id] : undefined;
  const detailStatus = detailNode ? statusOf(detailNode.id) : "PENDING";

  return (
    <div className="flow-shell">
      <div className="flow-head">
        <div>
          <p className="flow-kicker">AGENT PIPELINE — START TO END</p>
          <h3>{graph.title}</h3>
          <p>{graph.subtitle}</p>
        </div>
        <div className="flow-clock">
          {busy ? (
            <>
              <strong>running…</strong>
              live
            </>
          ) : trace ? (
            <>
              <strong>{formatMs(trace.total_ms)}</strong>
              {trace.nodes.length} node{trace.nodes.length === 1 ? "" : "s"} recorded
            </>
          ) : (
            <>
              <strong>idle</strong>
              no run yet
            </>
          )}
        </div>
      </div>

      <div className="flow-scroll">
        <div
          className="flow-canvas"
          ref={canvasRef}
          style={{
            gridTemplateColumns: `repeat(${lanes}, max-content)`,
            gridTemplateRows: `repeat(${rows}, auto)`,
          }}
        >
          <svg className="flow-edges" aria-hidden="true">
            {paths.map((p) => (
              <path key={p.key} d={p.d} className={p.cls} />
            ))}
          </svg>

          {graph.nodes.map((node) => {
            const status = statusOf(node.id);
            const run = runById[node.id];
            return (
              <button
                key={node.id}
                type="button"
                ref={(el) => {
                  nodeRefs.current[node.id] = el;
                }}
                className={`flow-node${selected === node.id ? " is-selected" : ""}`}
                data-status={status}
                style={{ gridColumn: node.lane + 1, gridRow: node.row + 1 }}
                onClick={() => setSelected(node.id === selected ? null : node.id)}
                aria-pressed={selected === node.id}
                title={node.description}
              >
                <span className="flow-node-kind">{KIND_LABEL[node.kind] ?? node.kind}</span>
                <span className="flow-node-label">{node.label}</span>
                <span className="flow-node-foot">
                  <span className="flow-node-status">{STATUS_WORD[status] ?? status}</span>
                  <span className="flow-node-ms">{formatMs(run?.duration_ms)}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {detailNode && (
        <div className="flow-detail">
          <div className="flow-detail-head">
            <strong>{detailNode.label}</strong>
            <span className={`flow-badge ${detailStatus.toLowerCase()}`}>
              {STATUS_WORD[detailStatus] ?? detailStatus}
            </span>
            {detailRun?.duration_ms != null && (
              <span className="flow-badge pending">{formatMs(detailRun.duration_ms)}</span>
            )}
          </div>

          <p className="flow-detail-desc">{detailNode.description}</p>

          {detailRun?.detail ? (
            <p
              className={`flow-detail-run${
                detailStatus === "REFUSED" || detailStatus === "FAILED"
                  ? " is-refused"
                  : detailStatus === "DEGRADED"
                    ? " is-degraded"
                    : ""
              }`}
            >
              {detailRun.detail}
            </p>
          ) : (
            <p className="flow-detail-run" style={{ color: "#7b8b89" }}>
              This node has not run yet in this session.
            </p>
          )}

          {metricPairs(detailRun?.metrics).length > 0 && (
            <ul className="flow-metrics">
              {metricPairs(detailRun?.metrics).map(([key, value]) => (
                <li key={key}>
                  {key} <b>{value}</b>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flow-legend">
        <span>
          <i style={{ background: "#2d7064" }} /> ran
        </span>
        <span>
          <i style={{ background: "#a65e38" }} /> degraded — ran, but not fully
        </span>
        <span>
          <i style={{ background: "#b9c6c2" }} /> skipped — click to see why
        </span>
        <span>
          <i style={{ background: "#a33d31" }} /> refused or failed
        </span>
        <span>
          <i
            style={{
              background: "transparent",
              borderTop: "2px dashed #4e8a7a",
              height: 0,
              width: 18,
            }}
          />{" "}
          runs in parallel
        </span>
      </div>
    </div>
  );
}
