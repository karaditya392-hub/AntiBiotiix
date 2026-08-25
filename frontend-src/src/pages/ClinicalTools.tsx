import { useEffect, useState } from "react";
import { BookOpenCheck, ShieldCheck, Search, Activity, FileText } from "lucide-react";
import UnifiedHeader from "@/components/UnifiedHeader";
import Console from "@/pages/Console";
import "@/styles/patient-dashboard.css";

type ToolModule = "tab-guidelines" | "tab-ask" | "tab-prescription" | "tab-audit" | "tab-reference";

export default function ClinicalTools() {
  const [activeModule, setActiveModule] = useState<ToolModule>("tab-guidelines");

  function switchModule(tabId: ToolModule) {
    setActiveModule(tabId);
    // Dispatch click to underlying nav-tab inside Console DOM
    setTimeout(() => {
      const tabBtn = document.querySelector(`.nav-tab[data-tab="${tabId}"]`) as HTMLElement;
      if (tabBtn) {
        tabBtn.click();
      } else {
        document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
        const target = document.getElementById(tabId);
        if (target) target.classList.add("active");
      }
    }, 50);
  }

  useEffect(() => {
    switchModule(activeModule);
  }, []);

  return (
    <main className="dashboard-page" data-standalone-tools="">
      {/* SINGLE UNIFIED TOP HEADER */}
      <UnifiedHeader />

      {/* PAGE TITLE & DESCRIPTION */}
      <div style={{ marginBottom: "20px" }}>
        <p className="dashboard-kicker">ANTIBIOTIX CLINICAL UTILITY PATH</p>
        <h1 style={{ fontFamily: "Space Grotesk, sans-serif", fontSize: "2rem", color: "#173c3d", margin: "4px 0" }}>
          Clinical Tools
        </h1>
        <p className="dashboard-subtitle" style={{ fontSize: "0.92rem" }}>
          Standalone clinical decision support utilities for guideline lookup, evidence search, prescription safety analysis, audit verification, and clinical reference.
        </p>
      </div>

      {/* 5 MODULE SELECTION GRID */}
      <section className="info-section" style={{ marginBottom: "20px" }}>
        <div className="section-title-row" style={{ marginBottom: "12px" }}>
          <div>
            <p className="dashboard-kicker">MODULE SELECTOR</p>
            <h2>Select Utility Module</h2>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "10px" }}>
          <button
            className={`dashboard-button ${activeModule === "tab-guidelines" ? "primary" : "secondary"}`}
            onClick={() => switchModule("tab-guidelines")}
            style={{ justifyContent: "center", padding: "12px 14px" }}
          >
            <BookOpenCheck size={16} /> Guidelines & Rules
          </button>

          <button
            className={`dashboard-button ${activeModule === "tab-ask" ? "primary" : "secondary"}`}
            onClick={() => switchModule("tab-ask")}
            style={{ justifyContent: "center", padding: "12px 14px" }}
          >
            <Search size={16} /> Ask the Evidence
          </button>

          <button
            className={`dashboard-button ${activeModule === "tab-prescription" ? "warning" : "secondary"}`}
            onClick={() => switchModule("tab-prescription")}
            style={{ justifyContent: "center", padding: "12px 14px" }}
          >
            <ShieldCheck size={16} /> Prescription Safety Engine
          </button>

          <button
            className={`dashboard-button ${activeModule === "tab-audit" ? "primary" : "secondary"}`}
            onClick={() => switchModule("tab-audit")}
            style={{ justifyContent: "center", padding: "12px 14px" }}
          >
            <Activity size={16} /> Audit Trail & Alert Fatigue
          </button>

          <button
            className={`dashboard-button ${activeModule === "tab-reference" ? "primary" : "secondary"}`}
            onClick={() => switchModule("tab-reference")}
            style={{ justifyContent: "center", padding: "12px 14px" }}
          >
            <FileText size={16} /> Clinical Reference
          </button>
        </div>
      </section>

      {/* CLEAN TOOL CONTENT CONTAINER (OLD CONSOLE SHELL REMOVED VIA CSS) */}
      <section className="info-section" style={{ background: "#ffffff", padding: "20px", borderRadius: "8px" }}>
        <Console view="entry" />
      </section>
    </main>
  );
}
