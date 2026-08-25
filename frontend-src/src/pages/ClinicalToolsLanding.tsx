import { BookOpenCheck, ShieldCheck, Search, Activity, FileText, ArrowRight } from "lucide-react";
import { Link } from "wouter";
import ClinicalToolsLayout from "@/components/ClinicalToolsLayout";
import "@/styles/patient-dashboard.css";

export default function ClinicalToolsLanding() {
  const tools = [
    {
      id: "guidelines",
      title: "Guidelines & Rules",
      path: "/clinical-tools/guidelines",
      icon: BookOpenCheck,
      color: "#2d7064",
      description: "Browse 2,276 indexed ICMR & WHO guideline passages, deterministic safety rules, input conditions, and governance review state.",
    },
    {
      id: "evidence",
      title: "Ask the Evidence",
      path: "/clinical-tools/evidence",
      icon: Search,
      color: "#2d7064",
      description: "Natural language extractive search over WHO AWaRe 2023, ICMR STGs, and FDA regulatory drug label evidence corpus.",
    },
    {
      id: "safety",
      title: "Prescription Safety Engine",
      path: "/clinical-tools/safety",
      icon: ShieldCheck,
      color: "#a65e38",
      description: "Execute the 24 deterministic clinical safety rules for allergy cross-reactivity, renal/hepatic dosing, DDIs, and stewardship.",
    },
    {
      id: "audit",
      title: "Audit Trail & Alert Fatigue",
      path: "/clinical-tools/audit",
      icon: Activity,
      color: "#2d7064",
      description: "Verify SHA-256 hash-chained audit logs, cryptographic integrity checks, clinician overrides, and alert fatigue recalibration metrics.",
    },
    {
      id: "reference",
      title: "Clinical Reference",
      path: "/clinical-tools/reference",
      icon: FileText,
      color: "#2d7064",
      description: "Explore ICMR STG 2022-23 syndromes, ICMR STW 2022 conditions, national AMR surveillance antibiograms, and guideline precedence rules.",
    },
  ];

  return (
    <ClinicalToolsLayout>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px" }}>
        {tools.map((t) => {
          const Icon = t.icon;
          return (
            <Link
              key={t.id}
              href={t.path}
              style={{
                background: "#fbfcf9",
                border: "1.5px solid #cbd9d4",
                borderRadius: "8px",
                padding: "24px",
                textDecoration: "none",
                color: "#203236",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                boxShadow: "0 2px 6px rgba(0,0,0,0.02)",
                transition: "all 0.15s ease",
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "10px" }}>
                  <div style={{ background: "#eef6f2", padding: "8px", borderRadius: "6px" }}>
                    <Icon size={22} color={t.color} />
                  </div>
                  <h3 style={{ margin: 0, fontFamily: "Space Grotesk, sans-serif", fontSize: "1.15rem", color: "#173c3d" }}>
                    {t.title}
                  </h3>
                </div>
                <p style={{ margin: "8px 0 16px", fontSize: "0.84rem", color: "#526968", lineHeight: 1.5 }}>
                  {t.description}
                </p>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "6px", color: t.color, fontWeight: 700, fontSize: "0.82rem" }}>
                Open Tool <ArrowRight size={15} />
              </div>
            </Link>
          );
        })}
      </div>
    </ClinicalToolsLayout>
  );
}
