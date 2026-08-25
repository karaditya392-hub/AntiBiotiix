import React from "react";
import { useLocation } from "wouter";
import { useAuth } from "@/context/AuthContext";
import UnifiedHeader from "@/components/UnifiedHeader";
import "@/styles/patient-dashboard.css";

interface ProtectedRouteProps {
  component: React.ComponentType<any>;
  path: string;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ component: Component }) => {
  const { isAuthenticated, isLoading } = useAuth();
  const [location, setLocation] = useLocation();

  React.useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      // Redirect unauthenticated doctor to login with current location as redirect param
      setLocation(`/login?redirect=${encodeURIComponent(location)}`);
    }
  }, [isAuthenticated, isLoading, location, setLocation]);

  if (isLoading) {
    return (
      <main className="dashboard-page">
        <UnifiedHeader />
        <div style={{ textAlign: "center", padding: "60px 20px" }}>
          <p style={{ fontSize: "1rem", color: "#173c3d", fontWeight: 600 }}>Verifying clinician authentication status...</p>
        </div>
      </main>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return <Component />;
};
