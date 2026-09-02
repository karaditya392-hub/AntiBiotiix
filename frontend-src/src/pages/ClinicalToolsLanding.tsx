import { BookOpenCheck, Bot, ShieldCheck, Search, FileText, ArrowRight } from "lucide-react";
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
      description: "Browse the indexed national and international guideline corpus, deterministic safety rules, input conditions, and governance review state.",
    },
    {
      id: "evidence",
      title: "Ask the Evidence",
      path: "/clinical-tools/evidence",
      icon: Search,
      color: "#2d7064",
      description: "Natural language extractive search over the ICMR and NCDC national antimicrobial guidelines, WHO AWaRe, the national programme guidelines, and FDA drug labels.",
    },
    {
      id: "agents",
      title: "Agent Console",
      path: "/clinical-tools/agents",
      icon: Bot,
      color: "#2d7064",
      description: "Run the two agent pipelines and watch them node by node: a document converted to Markdown, validated against guardrails and embedded; a query answered from the vector DB and the filtered web at once.",
    },
    {
      id: "safety",
      title: "Prescription Safety Engine",
      path: "/clinical-tools/safety",
      icon: ShieldCheck,
      color: "#a65e38",
      description: "Execute the 30 deterministic clinical safety rules for allergy cross-reactivity, renal/hepatic dosing, DDIs, vulnerable populations, and stewardship.",
    },
    {
      id: "reference",
      title: "Clinical Reference",
      path: "/clinical-tools/reference",
      icon: FileText,
      color: "#2d7064",
      description: "Explore ICMR STG syndromes, ICMR STW conditions, national AMR surveillance antibiograms, and the guideline precedence hierarchy.",
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
