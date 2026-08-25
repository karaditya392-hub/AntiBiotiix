import { Link, useLocation } from "wouter";
import { Stethoscope, Wrench, LogIn, LogOut, UserCheck } from "lucide-react";
import logoSrc from "@/assets/antibiotix-logo.jpg";
import { useAuth } from "@/context/AuthContext";
import "@/styles/patient-dashboard.css";

export default function UnifiedHeader() {
  const [location, setLocation] = useLocation();
  const { isAuthenticated, doctor, logout } = useAuth();

  const isStart = location === "/" || location === "/landing" || location === "/patient-type" || location.startsWith("/patients");
  const isClinicalTools = location.startsWith("/clinical-tools") || location.startsWith("/review");
  const isLogin = location === "/login";

  const handleLogout = () => {
    logout();
    setLocation("/login");
  };

  return (
    <header className="dashboard-header" style={{ marginBottom: "20px", alignItems: "center", justifyContent: "space-between" }}>
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

      <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
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

        {isAuthenticated && doctor ? (
          <div style={{ display: "flex", alignItems: "center", gap: "10px", background: "#f0f7f5", border: "1px solid #c2ded9", padding: "4px 10px", borderRadius: "6px" }}>
            <UserCheck size={16} color="#0f7774" />
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#173c3d", lineHeight: 1.1 }}>
                {doctor.display_name}
              </span>
              <span style={{ fontSize: "0.68rem", color: "#4f726e", fontWeight: 500 }}>
                {doctor.clinician_role.replace(/_/g, " ")}
              </span>
            </div>
            <button
              onClick={handleLogout}
              title="Log Out"
              style={{
                background: "transparent",
                border: "none",
                color: "#993a30",
                cursor: "pointer",
                padding: "4px",
                display: "flex",
                alignItems: "center",
                gap: "4px",
                fontSize: "0.75rem",
                fontWeight: 600,
                marginLeft: "4px",
              }}
            >
              <LogOut size={14} /> Exit
            </button>
          </div>
        ) : (
          <Link
            href="/login"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: isLogin ? "#0f7774" : "#f0f7f5",
              color: isLogin ? "#ffffff" : "#173c3d",
              border: "1px solid #173c3d",
              padding: "6px 12px",
              borderRadius: "6px",
              fontSize: "0.82rem",
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            <LogIn size={15} /> Doctor Login
          </Link>
        )}
      </div>
    </header>
  );
}
