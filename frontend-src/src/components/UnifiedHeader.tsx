import { Link, useLocation } from "wouter";
import { Stethoscope, Wrench } from "lucide-react";
import logoSrc from "@/assets/antibiotix-logo.jpg";
import "@/styles/patient-dashboard.css";

export default function UnifiedHeader() {
  const [location] = useLocation();

  const isStart = location === "/" || location === "/landing" || location === "/patient-type" || location.startsWith("/patients");
  const isClinicalTools = location.startsWith("/clinical-tools") || location.startsWith("/review");

  return (
    <header className="dashboard-header" style={{ marginBottom: "20px", alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
        <Link href="/" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: "12px" }}>
          <img src={logoSrc} alt="AntiBioTix" style={{ width: "36px", height: "36px", borderRadius: "6px", objectFit: "cover" }} />
          <div>
            <span style={{ fontFamily: "Space Grotesk, sans-serif", fontSize: "1.5rem", fontWeight: 700, color: "#173c3d", lineHeight: 1 }}>
              ANTIBIOTIX
            </span>
            <span style={{ fontSize: "0.72rem", color: "#607371", fontWeight: 500, display: "block", marginTop: "2px" }}>
              Antibiotic Clinical Decision Support System
            </span>
          </div>
        </Link>
      </div>

      <nav style={{ display: "flex", gap: "6px", background: "#173c3d", padding: "6px 8px", borderRadius: "6px" }}>
        <Link
          href="/patient-type"
          className={`doctor-nav-tab ${isStart ? "active" : ""}`}
        >
          <Stethoscope size={15} /> Start
        </Link>
        <Link
          href="/clinical-tools"
          className={`doctor-nav-tab ${isClinicalTools ? "active" : ""}`}
        >
          <Wrench size={15} /> Clinical Tools
        </Link>
      </nav>
    </header>
  );
}
