import React, { useState } from "react";
import { useLocation } from "wouter";
import { Lock, User, AlertCircle, ArrowRight } from "lucide-react";
import UnifiedHeader from "@/components/UnifiedHeader";
import { useAuth } from "@/context/AuthContext";
import "@/styles/patient-dashboard.css";

export default function Login() {
  const [, setLocation] = useLocation();
  const { login } = useAuth();

  // Extract redirect target from URL query string if present
  const searchParams = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const redirectTarget = searchParams.get("redirect") || "/patient-type";

  const [doctorId, setDoctorId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!doctorId.trim() || !password) {
      setError("Please provide both Doctor ID and Password.");
      return;
    }

    setError(null);
    setSubmitting(true);

    const result = await login(doctorId, password);

    if (result.success) {
      setLocation(redirectTarget);
    } else {
      setError(result.error || "Authentication failed. Invalid Doctor ID or Password.");
    }
    setSubmitting(false);
  };

  return (
    <main className="dashboard-page">
      <UnifiedHeader />

      <section className="patient-type-container" style={{ marginTop: "30px", maxWidth: "520px" }}>
        <div className="patient-type-header" style={{ textAlign: "center" }}>
          <p className="dashboard-kicker">OAUTH 2.0 AUTHENTICATION</p>
          <h1>Doctor Login Required</h1>
          <p>
            Please provide your authorized Doctor ID and Password to access patient records.
          </p>
        </div>

        <div
          className="patient-type-card"
          style={{
            background: "#ffffff",
            border: "1px solid #c9d8d5",
            borderRadius: "12px",
            padding: "32px",
            boxShadow: "0 12px 28px rgba(15,53,55,0.08)",
          }}
        >
          {error && (
            <div
              style={{
                background: "#fdf2f2",
                border: "1px solid #f8b4b4",
                color: "#9b1c1c",
                padding: "12px 16px",
                borderRadius: "8px",
                fontSize: "0.88rem",
                display: "flex",
                alignItems: "center",
                gap: "10px",
                marginBottom: "20px",
              }}
            >
              <AlertCircle size={18} style={{ flexShrink: 0 }} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
            <div>
              <label
                htmlFor="doctorId"
                style={{
                  display: "block",
                  fontSize: "0.82rem",
                  fontWeight: 700,
                  color: "#173c3d",
                  marginBottom: "6px",
                  letterSpacing: "0.03em",
                }}
              >
                DOCTOR ID / USERNAME
              </label>
              <div style={{ position: "relative" }}>
                <User
                  size={18}
                  style={{
                    position: "absolute",
                    left: "12px",
                    top: "50%",
                    transform: "translateY(-50%)",
                    color: "#607371",
                  }}
                />
                <input
                  id="doctorId"
                  type="text"
                  placeholder="e.g. DOC-ATTENDING-01"
                  value={doctorId}
                  onChange={(e) => setDoctorId(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "12px 12px 12px 40px",
                    borderRadius: "8px",
                    border: "1.5px solid #b2c7c3",
                    fontSize: "0.95rem",
                    color: "#0f3537",
                    background: "#f9fcfb",
                    outline: "none",
                  }}
                  required
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                style={{
                  display: "block",
                  fontSize: "0.82rem",
                  fontWeight: 700,
                  color: "#173c3d",
                  marginBottom: "6px",
                  letterSpacing: "0.03em",
                }}
              >
                PASSWORD
              </label>
              <div style={{ position: "relative" }}>
                <Lock
                  size={18}
                  style={{
                    position: "absolute",
                    left: "12px",
                    top: "50%",
                    transform: "translateY(-50%)",
                    color: "#607371",
                  }}
                />
                <input
                  id="password"
                  type="password"
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "12px 12px 12px 40px",
                    borderRadius: "8px",
                    border: "1.5px solid #b2c7c3",
                    fontSize: "0.95rem",
                    color: "#0f3537",
                    background: "#f9fcfb",
                    outline: "none",
                  }}
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="dashboard-button primary"
              style={{
                width: "100%",
                justifyContent: "center",
                padding: "14px",
                marginTop: "10px",
                fontSize: "0.95rem",
                fontWeight: 700,
                cursor: submitting ? "not-allowed" : "pointer",
                opacity: submitting ? 0.7 : 1,
              }}
            >
              {submitting ? "Verifying Credentials..." : "Log In to Access Patients"} <ArrowRight size={18} />
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
