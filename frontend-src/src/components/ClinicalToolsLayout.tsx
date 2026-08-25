import type { ReactNode } from "react";
import { Link, useLocation } from "wouter";
import { BookOpenCheck, ShieldCheck, Search, FileText } from "lucide-react";
import UnifiedHeader from "@/components/UnifiedHeader";
import "@/styles/patient-dashboard.css";

type Props = {
  children: ReactNode;
};

export default function ClinicalToolsLayout({ children }: Props) {
  const [location] = useLocation();

  const isGuidelines = location === "/clinical-tools/guidelines";
  const isEvidence = location === "/clinical-tools/evidence";
  const isSafety = location === "/clinical-tools/safety" || location === "/review/safety";
  const isReference = location === "/clinical-tools/reference";

  return (
    <main className="dashboard-page">
      {/* SINGLE UNIFIED TOP HEADER */}
      <UnifiedHeader />

      {/* PAGE TITLE & SUBTITLE */}
      <div style={{ marginBottom: "18px" }}>
        <p className="dashboard-kicker">ANTIBIOTIX CLINICAL UTILITY PATH</p>
        <h1 style={{ fontFamily: "Space Grotesk, sans-serif", fontSize: "2rem", color: "#173c3d", margin: "4px 0" }}>
          Clinical Tools
        </h1>
        <p className="dashboard-subtitle" style={{ fontSize: "0.92rem" }}>
          Standalone clinical decision support utilities for guideline lookup, evidence search, prescription safety analysis, and clinical reference.
        </p>
      </div>

      {/* SUB-NAVIGATION TAB BAR FOR THE 4 TOOLS */}
      <section className="info-section" style={{ marginBottom: "20px", padding: "14px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "10px" }}>
          <Link
            href="/clinical-tools/guidelines"
            className={`dashboard-button ${isGuidelines ? "primary" : "secondary"}`}
            style={{ justifyContent: "center", padding: "10px 12px" }}
          >
            <BookOpenCheck size={16} /> Guidelines & Rules
          </Link>

          <Link
            href="/clinical-tools/evidence"
            className={`dashboard-button ${isEvidence ? "primary" : "secondary"}`}
            style={{ justifyContent: "center", padding: "10px 12px" }}
          >
            <Search size={16} /> Ask the Evidence
          </Link>

          <Link
            href="/clinical-tools/safety"
            className={`dashboard-button ${isSafety ? "warning" : "secondary"}`}
            style={{ justifyContent: "center", padding: "10px 12px" }}
          >
            <ShieldCheck size={16} /> Prescription Safety Engine
          </Link>

          <Link
            href="/clinical-tools/reference"
            className={`dashboard-button ${isReference ? "primary" : "secondary"}`}
            style={{ justifyContent: "center", padding: "10px 12px" }}
          >
            <FileText size={16} /> Clinical Reference
          </Link>
        </div>
      </section>

      {/* MAIN TOOL CONTENT AREA */}
      <div>{children}</div>
    </main>
  );
}
